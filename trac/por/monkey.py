# -*- coding: utf-8 -*-

import logging

from por.models import DBSession
from por.dashboard.lib.helpers import unicodelower

log = logging.getLogger(__name__)


def is_inside_penelope():
    """
    This is a way to sense whether the components
    are run inside a web application or in trac-admin.
    """
    if DBSession.bind:
        return True
    return False


def fix_connection_init():
    """
    patch per gestire postgresql 9.x dve l'eccezione nella gestione degli
    schema e' cambiata (TODO: segnalare sul trac di trac.edgewall.org)
    """

    import psycopg2
    from psycopg2 import DataError, ProgrammingError as PGSchemaError
    from trac.db.util import ConnectionWrapper
    from trac.db.postgres_backend import assemble_pg_dsn, PostgreSQLConnection

    # l'eccezione ProgrammingError cambia in PGSchemaError
    def PostgreSQLConnection__init__(self, path, log=None, user=None, password=None, host=None,
                port=None, params={}):
        if path.startswith('/'):
            path = path[1:]
        if 'host' in params:
            host = params['host']

        cnx = psycopg2.connect(assemble_pg_dsn(path, user, password, host, port))

        cnx.set_client_encoding('UNICODE')
        try:
            self.schema = None
            if 'schema' in params:
                self.schema = params['schema']
                cnx.cursor().execute('SET search_path TO %s', (self.schema,))
                cnx.commit()
        # except (DataError, ProgrammingError):
        except PGSchemaError:
            cnx.rollback()
        except DataError:
            cnx.rollback()
        ConnectionWrapper.__init__(self, cnx, log)

    PostgreSQLConnection.__init__ = PostgreSQLConnection__init__



def fix_get_custom_fields():
    """
    patch per custom field con dati su por
    """

    import copy
    from trac.ticket.api import TicketSystem
    from por.models.dashboard import Project

    # TODO: cache ?
    # TODO: generalizzare
    def TicketSystem_get_custom_fields(self):
        if not is_inside_penelope():        # we are in trac-admin
            return self.custom_fields

        custom_fields = copy.deepcopy(self.custom_fields)
        project_id = self.config.get('por-dashboard', 'project-id')
        project = None
        if project_id:
            project = DBSession().query(Project).get(project_id)
        for field in custom_fields:
            if project and field['name'] == 'customerrequest':
                field['options'] = [cr.id for cr in sorted(project.customer_requests, key=unicodelower)]
                field['descriptions'] = dict([(cr.id, cr.name) for cr in project.customer_requests])
        # TODO: rimuovere il metodo sotto che invalida la cache, trovare
        # un altro modo per mantenere aggiornati i dati
        self.reset_ticket_fields()
        return custom_fields

    TicketSystem.get_custom_fields = TicketSystem_get_custom_fields



def fix_send_user_error():
    """
    patch per 401/403
    """

    import sys
    from genshi.builder import Fragment, tag
    from trac.util.text import exception_to_unicode
    from trac.web.api import RequestDone
    from trac.util.text import to_unicode
    from trac.util.translation import _, tag_
    import trac.web.main

    def send_user_error(req, env, e):
        # See trac/web/api.py for the definition of HTTPException subclasses.
        if env:
            env.log.warn('[%s] %s' % (req.remote_addr, exception_to_unicode(e)))
        try:
            # We first try to get localized error messages here, but we
            # should ignore secondary errors if the main error was also
            # due to i18n issues
            title = _("Error")
            if e.reason:
                if title.lower() in e.reason.lower():
                    title = e.reason
                else:
                    title = _("Error: %(message)s", message=e.reason)
        except Exception:
            title = 'Error'
        # The message is based on the e.detail, which can be an Exception
        # object, but not a TracError one: when creating HTTPException,
        # a TracError.message is directly assigned to e.detail
        if isinstance(e.detail, Exception): # not a TracError
            message = exception_to_unicode(e.detail)
        elif isinstance(e.detail, Fragment): # markup coming from a TracError
            message = e.detail
        else:
            message = to_unicode(e.detail)
        data = {'title': title, 'type': 'TracError', 'message': message,
                'frames': [], 'traceback': None}
        if e.code == 403 and req.authname == 'anonymous':
            # TRANSLATOR: ... not logged in, you may want to 'do so' now (link)
            do_so = tag.a(_("do so"), href=req.href.login())
            req.chrome['notices'].append(
                tag_("You are currently not logged in. You may want to "
                    "%(do_so)s now.", do_so=do_so))
            # MONKEY PATCH HERE !!!
            e.code = 401
        try:
            req.send_error(sys.exc_info(), status=e.code, env=env, data=data)
        except RequestDone:
            pass

    trac.web.main._send_user_error = send_user_error



def fix_get_known_users():
    """
    patch per known_user su por
    """

    from trac.env import Environment
    from por.models.dashboard import Project, User

    # TODO: cache ?
    # TODO: esistono api piu' semplici su por per la stessa richiesta?
    def Environment_get_known_users(self, cnx=None):
        project_id = self.config.get('por-dashboard', 'project-id')
        project = None
        if project_id:
            db = DBSession()
            project = db.query(Project).get(project_id)
            for user in db.query(User).all():
                if user.roles_in_context(project):
                    yield user.login, user.fullname, user.email

    Environment.get_known_users = Environment_get_known_users



def fix_customer_request_changelog_description():
    """
    Look up Customer Request description while creating change summaries (both web and email)
    """

    from trac.ticket.web_ui import TicketModule
    from por.models.dashboard import CustomerRequest

    _grouped_changelog_entries = TicketModule.grouped_changelog_entries
    def TicketModule_grouped_changelog_entries(self, ticket, db, when=None):
        ret = _grouped_changelog_entries(self, ticket, db, when)
        for item in ret:
            try:
                cr = item['fields']['customerrequest']
                qry = DBSession().query(CustomerRequest)
                old_cr = qry.get(cr['old'])
                new_cr = qry.get(cr['new'])
                cr['old'] = old_cr.name if old_cr else cr['old']
                cr['new'] = new_cr.name if new_cr else cr['new']
            except KeyError:
                pass

            yield item

    TicketModule.grouped_changelog_entries = TicketModule_grouped_changelog_entries



def fix_customer_request_dropdown():
    """
    Renders the CR dropdown options grouping them by state
    """

    from trac.ticket.web_ui import TicketModule
    from por.models.dashboard import CustomerRequest

    group_order = ['estimated', 'created','scheduled', 'achieved', 'invoiced']

    def group_sortkey(group):
        try:
            return group_order.index(group['label'])
        except ValueError:
            return -1

    def prepare_customerrequest_options(field):
        qry = DBSession.query(CustomerRequest)
        options = field['options']
        customer_requests = [qry.get(op) for op in options]
        groups = {}
        for cr in sorted(customer_requests, key=unicodelower):
            if cr is None: # the CR has probably been deleted
                continue
            groups.setdefault(cr.workflow_state, {
                                    'label': cr.workflow_state,
                                    'options': [],
                                    'descriptions': [],
                                })
            groups[cr.workflow_state]['options'].append(cr.id)
            groups[cr.workflow_state]['descriptions'].append(cr.name)
        field['options'] = []
        field['descriptions'] = []
        field['optgroups'] = sorted(groups.values(), key=group_sortkey)
        field['optional'] = True

    _prepare_fields = TicketModule._prepare_fields
    def TicketModule_prepare_fields(self, req, ticket):
        ret = _prepare_fields(self, req, ticket)
        for field in ret:
            if field['name'] == 'customerrequest':
                prepare_customerrequest_options(field)

        return ret

    TicketModule._prepare_fields = TicketModule_prepare_fields





def fix_filter_email_recipents():
    """
    FIX: per evitare mail al customer relativamente a commenti privati e ticket sensibili
    """
    from trac.ticket.notification import TicketNotifyEmail
    from trac.ticket.web_ui import TicketModule
    from trac.perm import PermissionSystem
    try:
        import privatecomments; privatecomments
        HAS_PRIVATECOMMENTS = True
    except ImportError:
        HAS_PRIVATECOMMENTS = False


    TicketNotifyEmail._orig_get_recipients = TicketNotifyEmail.get_recipients
    
    def TicketNotifyEmail_get_recipients(self, tktid):
        (torecipients, ccrecipients) = self._orig_get_recipients(tktid)
        perm = PermissionSystem(self.env)
        # sensitivetickets
        if self.ticket['sensitive'] == '1':
            def has_sensisitive_perm(username):
                return perm.get_user_permissions(username).get('SENSITIVE_VIEW')
            torecipients = filter(has_sensisitive_perm, torecipients)
            ccrecipients = filter(has_sensisitive_perm, ccrecipients)            
        # privatecomments
        if HAS_PRIVATECOMMENTS:
            privatecomment = False
            for mod in TicketModule(self.env).grouped_changelog_entries(self.ticket, self.db, self.modtime):
                cursor = self.db.cursor()
                sql = 'SELECT private FROM private_comment WHERE ticket_id=%d AND comment_id=%d AND private>0'
                cursor.execute(sql % (int(self.ticket.id), int(mod.get('cnum'))))
                if cursor.cursor.rowcount:
                    privatecomment = True
                cursor.close()
            if privatecomment:
                def has_privatecommente_perm(username):
                    return perm.get_user_permissions(username).get('PRIVATE_COMMENT_PERMISSION')
                torecipients = filter(has_privatecommente_perm, torecipients)
                ccrecipients = filter(has_privatecommente_perm, ccrecipients)                    
        return (torecipients, ccrecipients)
        
    TicketNotifyEmail.get_recipients = TicketNotifyEmail_get_recipients 





def fix_notification_props():
    """
    Change the table of ticket properties printed in notifications.
    """
    from trac.ticket.notification import TicketNotifyEmail
    from trac.util.text import wrap

    def iter_props(self):
        tkt = self.ticket
        yield '--'

        for f in tkt.fields:
            fname = f['name']

            if fname in ['summary', 'cc', 'time', 'changetime', 'qa1', 'qa2', 'sensitive', 'esogeno', 'customerrequest']:
                continue

            fval = tkt[fname] or ''
            if fname in ['owner', 'reporter']:
                fval = self.obfuscate_email(fval)

            flabel = f['label']

            if not fval:
                continue

            if f['type'] == 'textarea':
                yield u'%s:' % flabel
                for line in fval.split('\n'):
                    yield u'      %s' % line
            else:
                yield u'%s: %s' % (flabel, fval)


    def TicketNotifyEmail_format_props(self):
        return '\n'.join(iter_props(self))

    TicketNotifyEmail.format_props = TicketNotifyEmail_format_props





log.info("Monkey patch")
fix_connection_init()
fix_get_custom_fields()
fix_send_user_error()
fix_get_known_users()
fix_customer_request_changelog_description()
fix_customer_request_dropdown()
fix_filter_email_recipents()
fix_notification_props()

