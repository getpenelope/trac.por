# cluemapper 0.8.4
from pkg_resources import resource_filename
from trac import core as traccore
from trac.admin import api as adminapi
from trac.web import chrome
from trac.util.translation import _
from trac.ticket.notification import TicketNotificationSystem
from trac.notification import NotificationSystem


class CommunicationAdminPanel(traccore.Component):
    traccore.implements(adminapi.IAdminPanelProvider,
                        chrome.ITemplateProvider)

    def render_admin_panel(self, req, cat, page, path_info):
        message = None

        notsys_ticket = TicketNotificationSystem(self.env)
        notsys_general = NotificationSystem(self.env)

        data = {'message': message}

        if req.args.get('communication_applied', False):
            self.config.set('notification', 'always_notify_owner',
                            req.args.get('owner', False) == '1')
            self.config.set('notification', 'always_notify_updater',
                            req.args.get('updater', False) == '1')
            self.config.set('notification', 'always_notify_reporter',
                            req.args.get('reporter', False) == '1')
            # POR
            self.config.set('notification', 'smtp_always_cc',
                            req.args.get('alwayscc', ''))

            self.config.set('notification', 'smtp_always_bcc',
                            req.args.get('alwaysbcc', ''))
                            
            self.config.save()
            notsys_ticket = TicketNotificationSystem(self.env)
            notsys_general = NotificationSystem(self.env)
            message = u'Communication saved'

        if notsys_ticket.always_notify_owner:
            data['owner'] = True
        if notsys_ticket.always_notify_updater:
            data['updater'] = True
        if notsys_ticket.always_notify_reporter:
            data['reporter'] = True
        data['alwayscc'] = notsys_general.smtp_always_cc
        data['alwaysbcc'] = notsys_general.smtp_always_bcc

        return 'admin-communication.html', data

    def get_admin_panels(self, req):
        if req.perm.has_permission('TRAC_ADMIN'):
            yield ('general', _('General'),
                   'communication', 'Communication')

    def get_htdocs_dirs(self):
        return []

    def get_templates_dirs(self):
        return [resource_filename(__name__, 'templates')]

