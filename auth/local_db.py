import hashlib
import os.path
import provider
import logging

logger = logging.getLogger("auth")

class InMemoryDb(provider.AuthenticationProvider):
    """
        @summary: 
    """

    def __init__(self, loginMap, hashmethod = None):
        self.hash_method = hashmethod
        self.credentials = loginMap
        
    def authenticate(self, login, domain, password):
        if self.hash_method:        
            hasher = self.hash_method()
            hasher.update(password)
            computed = hasher.hexdigest()
        else:
            computed = password
        
        if not self.credentials.has_key(login):
            return False
        
        return self.credentials[login] == computed

    def canListUsers(self):
        return True
    
    def haveUser(self, login, domain):
        return self.credentials.has_key(login)
    

class FileDb(InMemoryDb):
    """
        @summary: 
    """
    
    def __init__(self, path, hashmethod = hashlib.sha1):
        super(FileDb, self).__init__(None, hashmethod)
        self.file_path = path
        self.file_mtime = 0

    def load_pass_file(self, path):
        try:
            self.credentials = {}
            for l in open(path, "r").readlines():
                tokens = l.strip().split(':', 2)
                if len(tokens) != 2:
                    continue
                
                (user, h) = tokens 
                if not user or not h:
                    continue
                
                self.credentials[user] = h
        except Exception, e:
            self.credentials = None
            logger.error("error loading cred file %s: %s" % (path, e))
            return False
        
        return True
    
    def authenticate(self, login, domain, password):
        if not os.path.exists(self.file_path):
            logger.error("file %s doesn't exist" % self.file_path) 
            return False
        
        mtime = os.path.getmtime(self.file_path)
        if not self.credentials or (mtime > self.file_mtime):
            if not self.load_pass_file(self.file_path):
                logger.error("unable to load/reload the password file")
                return False
            self.file_mtime = mtime
            
        return super(FileDb, self).authenticate(login, domain, password)
    
