from provider import AuthenticationProvider


class CascadingProvider(AuthenticationProvider):
    '''
        @summary: this provider is used to combine many providers in a single one.
            The resulting provider will authenticate asking to a list of given
            providers, once we have managed to authenticate against a provider
            the user is authenticated.
    '''

    def __init__(self, providers, uniqueUser = True):
        '''
            Constructor for a CascadingProvider. The uniqueUser argument is used
            to tell if a given login is registered only in a single provider. If
            it's the case it means that if the user is present in a provider and the
            authentication failed, we don't need to test the next ones
            
            @param providers: the list of providers
            @param uniqueUser: if a login is present only in a provider  
        '''
        self.providers = providers
        self.listUsersAbility = True
        self.uniqueUser = uniqueUser
        
        for p in providers:
            if not p.canListUsers():
                self.listUsersAbility = False
                break
    
    def canListUsers(self):
        return self.listUsersAbility
    
    def haveUser(self, login, domain):
        if not self.listUsersAbility:
            return False
        
        for p in self.providers:
            if p.haveUser(login, domain):
                return True
        return False
    
    def authenticate(self, login, domain, password):
        for p in self.providers:
            if p.authenticate(login, domain, password):
                return True
            
            if self.uniqueUser and p.canListUsers() and p.haveUser(login, domain):
                return False
    
        return False
    
    

class DomainMapProvider(AuthenticationProvider):
    '''
        @summary: this provider maps a provider for a domain
    '''
    
    def __init__(self, domainMap, defaultProvider=None):
        self.domainMap = domainMap
        self.listUsersAbility = True
        self.defaultProvider = defaultProvider
        
        for p in domainMap.values():
            if not p.canListUsers():
                self.listUsersAbility = False
                break
            
        if defaultProvider and not defaultProvider.canListUsers():
            self.listUsersAbility = False
            
                 
    def canListUsers(self):
        return self.listUsersAbility
    
    def haveUser(self, login, domain):
        if not self.listUsersAbility:
            return False
        
        provider = self.domainMap.get(domain, None)
        if provider:
            return provider.haveUser(login, domain)
        
        if not self.defaultProvider:
            return False
        
        return self.defaultProvider.haveUser(login, domain)
            
    def authenticate(self, login, domain, password):
        provider = self.domainMap.get(domain, None)
        if provider:
            return provider.authenticate(login, domain, password)
        
        if not self.defaultProvider:
            return False
    
        return self.defaultProvider.authenticate(login, domain, password)
    