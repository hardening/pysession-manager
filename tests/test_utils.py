import unittest
from content_provider import expandVars

class Test(unittest.TestCase):


    def testExpandVars(self):
        context = {
            "user": "user"
        }
        self.assertEquals(expandVars("/var/run/${user}", context), "/var/run/user") 
        


if __name__ == "__main__":
    #import sys;sys.argv = ['', 'Test.testName']
    unittest.main()