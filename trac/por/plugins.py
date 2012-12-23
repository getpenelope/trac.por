# -*- coding: utf-8 -*-

import datetime
import json
import operator
import pkg_resources
import re
import urllib

import sqlalchemy.orm.exc

from genshi.builder import tag
from genshi.core import TEXT
from genshi.output import TextSerializer
from genshi.filters.transform import Transformer

from trac.core import Component
from trac.core import implements
from trac.resource import Resource
from trac.ticket import query
from themeengine.api import ThemeBase
from tracrpc.api import IXMLRPCHandler
from trac.web.api import IRequestFilter, ITemplateStreamFilter, IRequestHandler
from trac.ticket.api import TicketSystem
from trac.web.chrome import ITemplateProvider, add_script, add_script_data, add_stylesheet, Chrome
from trac.ticket.web_ui import TicketModule

from por.dashboard.fanstatic_resources import dashboard
from por.dashboard.fanstatic_resources import add_entry_from_ticket
from por.models import DBSession
from por.models.dashboard import CustomerRequest, Project, User
from por.models.tp import TimeEntry
from por.models.tp import timedelta_as_human_str
from genshi import Markup

from trac.por.i18n import add_domains



def del_script(req, script):
    if not req.chrome.get('scripts'):
        return False
    req.chrome['scripts'] = \
        [s for s in req.chrome['scripts'] \
            if not s.get('href', '').endswith(script)]


def del_style(req, script):
    all_styles = req.chrome['links']['stylesheet']
    new_styles = [
            s for s in all_styles
            if not s.get('href', '').endswith(script)
            ]
    if new_styles != all_styles:
        req.chrome['links']['stylesheet'] = new_styles
        return True
    return False


class PorTheme(ThemeBase):
    """A theme for Trac"""
    template = htdocs = css = True

    def __init__(self):
        add_domains(self.env.path)



class PorNav(Component):
    """ add custom breadcrumbs """
    implements(ITemplateStreamFilter)


    # ITemplateStreamFilter methods
    # TODO: cache
    # TODO: c'è un metodo per ricavare le url del customer e del project?
    def filter_stream(self, req, method, filename, stream, data):
        project_id = self.env.config.get('por-dashboard', 'project-id')
        if project_id:
            project = DBSession().query(Project).get(project_id)
            # XXX se project is None, 404

            stream |= Transformer(".//div[@id='trac-before-subnav']").prepend(tag.ul(
                    tag.li(tag.a("Home", href="/")),
                    tag.li(
                            tag.span(" / ", class_="divider"),
                            tag.a(project.customer.name, href="/admin/Customer/%s" % project.customer.id)
                        ),
                    tag.li(
                            tag.span(" / ", class_="divider"),
                            tag.a(project.name, href="/admin/Project/%s" % project.id)
                        ),
                    tag.li(
                            tag.span(" / ", class_="divider"),
                            tag.a('Trac', href="/trac/%s" % project.id),
                            class_='active'
                        ),
                    class_="breadcrumb noprint",
                ))

        return stream



class PorFanstatic(Component):
    """ """
    implements(IRequestFilter, ITemplateProvider)

    # ITemplateProvider methods
    def get_htdocs_dirs(self):
        return [('por', pkg_resources.resource_filename(__name__, 'htdocs'))]

    def get_templates_dirs(self):
        return [pkg_resources.resource_filename(__name__, 'templates')]

    # IRequestFilter methods
    def pre_process_request(self, req, handler):
        return handler

    def post_process_request(self, req, template, data, content_type):
        # remove script (jquery aggiornato caricato via fanstatic)
        del_script(req, 'common/js/jquery.js')
        # fanstatic
        dashboard.need()
        add_script(req, 'por/por.js')
        field_descriptions = dict([(field['name'], field['descriptions']) \
            for field in TicketSystem(self.env).get_custom_fields() \
                if field.get('descriptions')])
        add_script_data(req, {'fielddescriptions': field_descriptions})
        return template, data, content_type



class RescopedCSS(Component):
    """ """
    implements(IRequestFilter)

    def pre_process_request(self, req, handler):
        return handler

    def post_process_request(self, req, template, data, content_type):
        # TODO see what's available at runtime
        for cssfile in ['about.css', 'admin.css', 'browser.css', 'changeset.css', 'code.css',
                        'diff.css', 'prefs.css', 'report.css', 'roadmap.css', 'search.css',
                        'ticket.css', 'timeline.css', 'trac.css', 'wiki.css']:
            if del_style(req, 'common/css/%s' % cssfile):
                add_stylesheet(req, 'por/rescoped-css/%s' % cssfile)
        return template, data, content_type



class PorTimeEntry(Component):
    """
    Adds the required javascript for the feature "Add Time Entry from Ticket".
    """
    implements(IRequestFilter)

    # IRequestFilter methods
    def pre_process_request(self, req, handler):
        return handler

    def post_process_request(self, req, template, data, content_type):
        if template == 'ticket.html' and req.perm.has_permission('TIME_ENTRY_ADD'):
            add_entry_from_ticket.need()
        return template, data, content_type




class PorModifySimple(Component):
    """
    Hides (not remove) some fields from the Modify Ticket if the user is a customer.
    """
    implements(IRequestFilter)

    # IRequestFilter methods
    def pre_process_request(self, req, handler):

        if req.perm.has_permission('SENSITIVE_VIEW'):       # XXX right permission here
            hidden_cls = 'hidden-to-customers'
        else:
            hidden_cls = 'hide'

        field_classes = [
            ('type', ''),
            ('priority', ''),
            ('customerrequest', ''),
            ('cc', ''),
            ('keywords', ''),
            ('milestone', ''),
            ('qa1', ''),
            ('qa2', ''),
            ('fasesviluppo', ''),
            ('issuetype', hidden_cls),
            ('esogeno', hidden_cls),
            ('version', hidden_cls),
            ('component', hidden_cls),
            ('blocking', hidden_cls),
            ('blockedby', hidden_cls),
            ('sensitive', hidden_cls)
            ]

        field_order = [f[0] for f in field_classes]

        def sortkey(field):
            try:
                return field_order.index(field['name'])
            except ValueError:
                return len(field_order) + 1000

        req.ticketfields_sortkey = sortkey
        req.ticketfields_classes = dict(field_classes)

        return handler

    def post_process_request(self, req, template, data, content_type):
        return template, data, content_type


class PorTicketTimeEntries(Component):
    """
    Render ticket timeentries
    """
    implements(IRequestFilter)

    # IRequestFilter methods
    def pre_process_request(self, req, handler):
        if isinstance(handler, Chrome):
            # return ASAP if we are serving a static resource
            return handler

        req.ticket_time_entries = []
        if isinstance(handler, TicketModule):
            project_id = self.env.config.get('por-dashboard', 'project-id')
            ticket_id = req.args.get('id', None)
            if ticket_id and project_id:
                timeentries = DBSession().query(TimeEntry)\
                               .filter_by(project_id=project_id)\
                               .filter_by(ticket=int(ticket_id)).order_by(TimeEntry.date.desc(), TimeEntry.modification_date.desc())
                delta = datetime.timedelta()
                delta_tot = sum([e.hours for e in timeentries], delta)
                req.ticket_time_entries_total = timedelta_as_human_str(delta_tot)
                req.ticket_time_entries = timeentries[:20]
                req.ticket_time_entries_count = timeentries.count()

        return handler

    def post_process_request(self, req, template, data, content_type):
        return template, data, content_type


class PorReportDropDown(Component):
    """
    Render report list as a bootstrap button/dropdown combo
    """
    implements(IRequestFilter)

    def _iter_reports(self):
        db = self.env.get_db_cnx()
        cursor = db.cursor()
        cursor.execute("SELECT id, title FROM report ORDER BY id")
        for row in cursor:
            yield row[0], row[1]
            if row[0] in (3, 6):
                yield None, None

    def genshi_text(self, stream, flag=False):
        """
        @author: mmariani, lucabel
        @description: we use this method in template 'cause we can't
        draw directly the elem from chrome.ctxtnav: it put a link in
        a button and we don't want that
        """
        return Markup(' '.join(TextSerializer()(stream)))

    # IRequestFilter methods
    def pre_process_request(self, req, handler):
        if isinstance(handler, Chrome):
            # return ASAP if we are serving a static resource
            return handler

        lis = []
        for report_id, report_name in self._iter_reports():
            lis.append({'name': report_name, 'href': req.href.report(report_id)})

        req.report_dropdown_elements = lis
        req.genshi_text = self.genshi_text

        return handler

    def post_process_request(self, req, template, data, content_type):
        return template, data, content_type



class PorUserEmailLookup(Component):
    """
    Replaces email in workflow actions with a fullname
    """
    implements(ITemplateStreamFilter)

    def email_lookup(self, text):
        try:
            user = DBSession.query(User).filter(User.email==text).one()
            return user.fullname
        except sqlalchemy.orm.exc.NoResultFound:
            return text

    def filter_stream(self, req, method, filename, stream, data):
        stream |= Transformer("//select[@id='action_review_reassign_owner']/option").map(self.email_lookup, TEXT)
        stream |= Transformer("//select[@id='action_reassign_reassign_owner']/option").map(self.email_lookup, TEXT)
        stream |= Transformer("//select[@name='0_owner']/option").map(self.email_lookup, TEXT)
        stream |= Transformer("//select[@name='field_owner']/option").map(self.email_lookup, TEXT)
        return stream



class TicketRPC(Component):
    """ An interface to Trac's ticketing system. """

    implements(IXMLRPCHandler)

    # IXMLRPCHandler methods
    def xmlrpc_namespace(self):
        return 'ticket'

    def xmlrpc_methods(self):
        yield (None, ((list,), (list, str)), self.queryWithDetails)
        yield (None, ((list,), (list, str)), self.queryCustomerRequestsByTicktes)
        yield (None, ((list,), (list, str)), self.queryAllCustomerRequests)

    # Exported methods
    def queryWithDetails(self, req, qstr='status!=closed'):
        """
        Perform a ticket query, returning a list of ticket dictionaries.
        All queries will use stored settings for maximum number of results per
        page and paging options. Use `max=n` to define number of results to
        receive, and use `page=n` to page through larger result sets. Using
        `max=0` will turn off paging and return all results.
        """
        # TODO: gestione custom id^= (workaround)
        if "id^=" in qstr:
            startswith = re.search('id\^=([\d]*)', qstr).group(1)
            qstr = re.sub('id\^=[\d]*', '', qstr)
            qstr = re.sub('^&|&$|&&', '', qstr)
            if "max=" in qstr:
                limit = re.search('max=([\d]*)', qstr).group(1)
                qstr = re.sub('max=[\d]*', 'max=0', qstr)
            else:
                limit = None
        else:
            startswith = None
            limit = None

        q = query.Query.from_string(self.env, qstr)
        ticket_realm = Resource('ticket')
        out = []
        for t in q.execute(req):
            tid = t['id']
            if not startswith or str(tid).startswith(startswith):
                if 'TICKET_VIEW' in req.perm(ticket_realm(id=tid)):
                    out.append(t)
                    if limit and len(out) >= limit:
                        break

        # fill 'resolution' value (it is not provided by the above query)
        db = self.env.get_db_cnx()
        cursor = db.cursor()
        cursor.execute("SELECT id, resolution FROM ticket WHERE status='closed'")
        
        resolution = {}
        for row in cursor:
            resolution[row[0]] = row[1]

        # fill 'sensitive' value (TODO optimize, as it now retrieves all tickets)
        db = self.env.get_db_cnx()
        cursor = db.cursor()
        cursor.execute("SELECT ticket, value FROM ticket_custom WHERE name='sensitive' AND value='1'")
        sensitive = set()
        for row in cursor:
            sensitive.add(row[0])

        # fill 'customerrequest' value (TODO optimize, as it now retrieves all tickets)
        cursor = db.cursor()
        cursor.execute("SELECT t.id AS ticket, c.value FROM ticket t INNER JOIN ticket_custom c ON (t.id = c.ticket AND c.name = 'customerrequest') order by ticket")
        cr= {}
        for row in cursor:
            cr[row[0]]=row[1]

        for t in out:
            t['sensitive'] = int(t['id'] in sensitive)
            t['resolution'] = resolution.get(t['id'], '')
            t['cr'] = cr.get(t['id'], '')

        return out

    def queryCustomerRequestsByTicktes(self, req, ticket_ids):
        """
            Args:
                ticket_ids: list of ticket ids

            Returns:
                list of tuples: ticket_id, customerrequest_field ('id> description')
        """
        db = self.env.get_db_cnx()
        cursor = db.cursor()
        cursor.execute("""SELECT ticket, value FROM ticket_custom
            WHERE name='customerrequest' AND ticket IN %(tickets)s;""",
                {'tickets': tuple(ticket_ids)})
        customer_request_ids = cursor.fetchall() or []
        db.rollback()
        return customer_request_ids

    def queryAllCustomerRequests(self, req):
        """
            Args:
                ticket_ids: list of ticket ids

            Returns:
                list of tuples: ticket_id, customerrequest_field
        """
        db = self.env.get_db_cnx()
        cursor = db.cursor()
        cursor.execute("SELECT ticket, value FROM ticket_custom WHERE name='customerrequest'")
        rows = cursor.fetchall() or []
        db.rollback()
        return rows



class SensitiveTicketsPolicy(Component):
    implements(ITemplateStreamFilter)

    # ITemplateStreamFilter methods
    def filter_stream(self, req, method, filename, stream, data):
        """Return a filtered Genshi event stream, or the original unfiltered
        stream if no match.

        `req` is the current request object, `method` is the Genshi render
        method (xml, xhtml or text), `filename` is the filename of the template
        to be rendered, `stream` is the event stream and `data` is the data for
        the current template.

        See the Genshi documentation for more information.
        """
        if filename == 'ticket.html':
            ticket = data['ticket']
            if ticket.exists:
                sensitive = (ticket.values.get('sensitive') == '1')
                if req.perm.has_permission('SENSITIVE_VIEW'):
                    action = data['ticket'].exists and \
                        req.href.ticket(data['ticket'].id) or \
                        req.href.newticket()
                    form = tag.form(
                        tag.input(
                            id="field-sensitive",
                            name="field_sensitive",
                            value=sensitive and '0' or '1',
                            type='hidden'),
                        tag.input(
                            type="hidden",
                            name="ts",
                            value=data['timestamp']),
                        tag.input(
                            type="hidden",
                            name="action",
                            value=data['action']),
                        tag.input(
                            type="submit",
                            name="submit",
                            class_='btn',
                            # TODO: translations
                            value=sensitive and 'make public' or 'make private'),
                        method="post",
                        id="sensitiveform",
                        action="%s#trac-modify-sensitive" % action,
                    )
                    if sensitive:
                        div = tag.div(
                            # TODO: translations
                            tag.div(
                                form,
                                # XXX i18n TODO tag.span(_("trac_por_ticket_sensitive"),
                                tag.span(u'Il ticket è riservato ai developer e non visibile al cliente',
                                         class_="sensitive-message"),
                                class_="alert alert-success"),
                            id='sensitiveticket')
                    else:
                        div = tag.div(
                            # TODO: translations
                            tag.div(
                                form,
                                # XXX i18n TODO tag.span(_("trac_por_ticket_public"),
                                tag.span(u'Ticket condiviso con il cliente',
                                         class_="sensitive-message"),
                                class_="alert alert-error"),
                            id='sensitiveticket')
                    return stream | \
                        Transformer("//div[@id='ticket']").before(div)
        return stream




class OutstandingTickets(Component):
    """
    Returns a JSON object with info about open tickets.
    """
    implements(IRequestHandler)

    def match_request(self, req):
        match = re.match(r'/outstanding_tickets/', req.path_info)
        if match:
            return True


    def iter_tickets(self, req, query_string):
        q = query.Query.from_string(self.env, query_string)
        ticket_realm = Resource('ticket')
        for t in sorted(q.execute(req), key=operator.itemgetter('changetime'), reverse=True):
            if 'TICKET_VIEW' in req.perm(ticket_realm(id=t['id'])):
                yield {
                    'id': t['id'],
                    'summary': t['summary'],
                    'status': t['status'],
                    'priority_value': t['priority_value'],
                    'href': t['href'],
                    }

    def process_request(self, req):
        qs = (
            'owner=%s'
            '&max=0'
            '&status=accepted'
            '&status=assigned'
            '&status=new'
            '&status=reopened'
            '&status=reviewing'
            )

        qs_own = qs % req.authname
        qs_unassigned = qs % ''

        tickets_own = list(self.iter_tickets(req, query_string=qs_own))
        tickets_unassigned = list(self.iter_tickets(req, query_string=qs_unassigned))

        data = json.dumps({
                    'tickets_own': tickets_own,
                    'query_url_own': '%s/query?%s' % (req.base_url, qs_own),
                    'tickets_unassigned': tickets_unassigned,
                    'query_url_unassigned': '%s/query?%s' % (req.base_url, qs_unassigned),
                    })
        req.send(data, 'application/json')



class CurrentIteration(Component):
    """
    Redirects to a precompiled custom query for active customer requests.
    """
    implements(IRequestHandler)

    def match_request(self, req):
        match = re.match(r'/current_iteration$', req.path_info)
        if match:
            return True


    def process_request(self, req):

        project_id = self.env.config.get('por-dashboard', 'project-id')

        qry = DBSession().query(CustomerRequest)
        qry = qry.filter(CustomerRequest.project_id==project_id)
        qry = qry.filter(CustomerRequest.placement==CustomerRequest.PLACEMENT_BOARD)
        qry = qry.filter(CustomerRequest.workflow_state.in_(['created', 'estimated']))

        query_params = {
                'owner': ['$USER', ''],
                'status': ['assigned', 'new', 'reopened', 'reviewing'],
                'group': 'customerrequest',
                'customerrequest': [ cr.id for cr in qry ],
                'col': ['id', 'summary', 'status', 'type', 'priority', 'component', 'customerrequest'],
                'order': 'priority',
                }

        query_string = urllib.urlencode(query_params, doseq=True)

        req.redirect('%s/query?%s' % (req.base_url, query_string))


