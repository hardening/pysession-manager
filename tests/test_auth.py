import unittest
import auth.compose
from auth.provider import YesProvider, NoProvider
from auth.local_db import InMemoryDb
from auth.compose import CascadingProvider
from hashlib import md5



class Test(unittest.TestCase):

    def testInMemory(self):
        p = InMemoryDb({"login": "password"})
        self.assertTrue(p.authenticate("login", "dom", "password"))
        self.assertFalse(p.authenticate("login", "dom", "bad password"))

        # same try with a hashed DB
        md = md5()
        md.update("password")
        p = InMemoryDb({"login": md.hexdigest()}, md5)
        self.assertTrue(p.authenticate("login", "dom", "password"))
        self.assertFalse(p.authenticate("login", "dom", "bad password"))

    def testCascade(self):
        p1 = InMemoryDb({"login": "password", "login2": "password in p1"})
        p2 = InMemoryDb({"login2": "password in p2"})
        
        # basic test
        c = CascadingProvider((p1, p2), False)
        self.assertTrue(c.authenticate("login2", "dom", "password in p1"))
        self.assertTrue(c.authenticate("login2", "dom", "password in p2"))
        
        # test unique login
        c = CascadingProvider((p1, p2), True)
        self.assertTrue(c.authenticate("login2", "dom", "password in p1"))
        self.assertFalse(c.authenticate("login2", "dom", "password in p2"))
        
    
    def testMap(self):
        p = auth.compose.DomainMapProvider({"yes": YesProvider(), "no": NoProvider()})
        
        self.assertFalse(p.authenticate("login", "no", ""), "no domain")
        self.assertTrue(p.authenticate("login", "yes", ""), "yes domain")

        # ship a default provider
        p = auth.compose.DomainMapProvider({"yes": YesProvider(), "no": NoProvider()}, YesProvider())
        self.assertTrue(p.authenticate("login", "not yes, not no", ""))


if __name__ == "__main__":
    #import sys;sys.argv = ['', 'Test.testName']
    unittest.main()