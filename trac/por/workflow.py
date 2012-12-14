# -*- coding: utf-8 -*-
#
# http://trac-hacks.org/wiki/TicketValidatorPlugin
#

from trac.core import Component, implements
from trac.ticket.api import TicketSystem
from trac.ticket import ITicketManipulator

from trac.por.i18n import _


class TicketWorkflowGuards(Component):
    """ """

    implements(ITicketManipulator)

    def prepare_ticket(self, req, ticket, fields, actions):
        """Not currently called, but should be provided for future
           compatibility."""

    def validate_ticket(self, req, ticket):
        """Make sure required fields for the next state have been
           the ticket will be in have been entered."""

        state = self._get_state(req, ticket)

        errors = []
	if req.perm.has_permission('SENSITIVE_VIEW'):
	    if ticket['type'] == 'defect' and ticket['issuetype'] == '':
	        errors.append(('issuetype', 'Devi specificare la natura del problema se si tratta di un difetto'))
        
        if state == 'closed' and ticket['resolution'] in ('fixed',):
            if ticket['qa1'] == 'non attuata':
                # XXX i18n TODO errors.append(('qa1', _("trac_por_qa1_required")))
                errors.append(('qa1', 'Necessaria la verifica della soluzione prima della chiusura del ticket'))
            if ticket['qa2'] == 'non efficace':
                # XXX i18n TODO errors.append(('qa2', _("trac_por_qa2_required")))
                errors.append(('qa2', "Necessaria la verifica dell'efficacia della soluzione prima della chiusura del ticket"))

        return errors

    def _get_state(self, req, ticket):
        """Get the state this ticket is going to be in."""
        
        if 'action' not in req.args:
            return 'new'
        
        action = req.args['action']
        action_changes = {}
        
        for controller in self._get_action_controllers(req, ticket, action):
            action_changes.update(controller.get_ticket_changes(req, ticket, action))
        
        return 'status' in action_changes and action_changes['status'] or ticket['status']
        
    def _get_action_controllers(self, req, ticket, action):
        for controller in TicketSystem(self.env).action_controllers:
            actions = [action for weight, action in
                       controller.get_ticket_actions(req, ticket)]
            if action in actions:
                yield controller
                
