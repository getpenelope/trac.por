from trac import core
from trac.perm import IPermissionStore, DefaultPermissionStore, IPermissionGroupProvider

from por.models import DBSession
from por.models.dashboard import Project, User

 
class PorPermissionStore(DefaultPermissionStore):
    """ """
    core.implements(IPermissionStore, IPermissionGroupProvider)

    # IPermissionGroupProvider
    def get_permission_groups(self, username):
        # TODO: work only for por/trac on the same wsgi stack
        project_id = self.env.config.get('por-dashboard', 'project-id')
        if project_id:
            project = DBSession().query(Project).get(project_id)
            user = DBSession().query(User).filter_by(email=username).first()
            if user:
                return list(user.roles_in_context(context=project))
        return list() 

    # IPermissionStore
    def get_user_permissions(self, username):
        """Return all permissions for the user with the specified name.

        The permissions are returned as a dictionary where the key is the name
        of the permission, and the value is either `True` for granted
        permissions or `False` for explicitly denied permissions."""
        
        # TODO: work only for por/trac on the same wsgi stack
        actions = set(super(PorPermissionStore, self).get_user_permissions(username))
        project_id = self.env.config.get('por-dashboard', 'project-id')
        if project_id:
            project = DBSession().query(Project).get(project_id)
            user = DBSession().query(User).filter_by(email=username).first()
            if user:
                for role in user.roles_in_context(context=project):
                    actions.update(set(super(PorPermissionStore, self).get_user_permissions(role)))
        return list(actions) 

    # BBB: Trac dichiara questo metodo ma non mi risulta venga mai utilizzato
    
    # def get_users_with_permissions(self, permissions):
    #    """Retrieve a list of users that have any of the specified permissions.
    #
    #    Users are returned as a list of usernames.
    #    """

    # def get_all_permissions(self):
    #    """Return all permissions for all users.
    #   
    #    The permissions are returned as a list of (subject, action)
    #   formatted tuples."""

    # def grant_permission(self, username, action):
    #    """Grant a user permission to perform an action."""

    # def revoke_permission(self, username, action):
    #    """Revokes the permission of the given user to perform an action."""

