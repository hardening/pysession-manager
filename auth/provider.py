
class AuthenticationProvider(object):
    '''
        @summary: base class for authentication providers
    '''
    
    def authenticate(self, login, domain, password):
        '''
            Authenticates a user
            
            @param login: the login of the connection user
            @param domain: the domain for this user
            @param password: the password to login
            @return if the authentication has completed successfully
        '''
        return True
    
    def canListUsers(self):
        ''' @return if this provider can list the users '''
        return False
    
    def haveUser(self, login, domain):
        ''' @return if the given login is a valid login '''
        return False
    

class YesProvider(AuthenticationProvider):
    '''
        @summary: a provider that always answers yes
    '''
    
    def authenticate(self, login, domain, password):
        return True

class NoProvider(AuthenticationProvider):
    '''
        @summary: a provider that always answers no
    '''
    
    def authenticate(self, login, domain, password):
        return False
    