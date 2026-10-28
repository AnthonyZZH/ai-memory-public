"""Check the exact real request payload without network or credentials."""
import argparse, sys, unittest
from pathlib import Path
p=argparse.ArgumentParser(); p.add_argument('--source',type=Path,required=True); p.add_argument('--work',type=Path,required=True)
a,rest=p.parse_known_args();sys.path.insert(0,str(a.source))
from social_brain import Brain
class ThinkingTests(unittest.TestCase):
    def test_default_off_and_explicit_on(self):
        settings={}; brain=Brain(settings,None); sent=[]
        brain.post=lambda payload:sent.append(payload)
        brain.request([{'role':'user','content':'synthetic'}])
        self.assertEqual(sent[-1].get('thinking'),{'type':'disabled'})
        settings['thinking']=True
        brain.request([{'role':'user','content':'synthetic'}])
        self.assertEqual(sent[-1].get('thinking'),{'type':'enabled'})
        self.assertNotIn('tools',sent[-1])
if __name__=='__main__': unittest.main(argv=[sys.argv[0],*rest])
