"""Synthetic persona/export tests. Retain fixtures on E:, never modify her/vault."""
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts'))
import persona_loader as loader
spec=importlib.util.spec_from_file_location('publisher',ROOT/'scripts/publish-public.py')
pub=importlib.util.module_from_spec(spec); spec.loader.exec_module(pub)


class PublicTests(unittest.TestCase):
    def setUp(self):
        base=Path('E:/Codex Development/tmp/v3.1b/public-tests'); base.mkdir(parents=True,exist_ok=True)
        self.work=Path(tempfile.mkdtemp(dir=base))
        self.her=self.work/'her'; self.her.mkdir()
        (self.her/'persona.md').write_text('## 身份\n- synthetic persona',encoding='utf-8')
        (self.her/'voice.md').write_text('## 说话\n- synthetic voice',encoding='utf-8')
        (self.her/'identity-lock.yaml').write_text('identity: [identity]\nprinciples: [principle]',encoding='utf-8')
        (self.her/'personality.json').write_text(json.dumps({'traits':{'示例':{'value':50}}}),encoding='utf-8')
        (self.her/'evolution').mkdir()
        (self.her/'evolution/expressions.md').write_text('- friendly phrase',encoding='utf-8')
        (self.her/'relationship.md').write_text('OWNER_ONLY_SENTINEL',encoding='utf-8')
        p=self.her/'evolution/proposals/pending'; p.mkdir(parents=True)
        (p/'pending.json').write_text(json.dumps({'trait':'示例','delta':1}),encoding='utf-8')
        self.vault=self.work/'vault'; self.vault.mkdir()
        self.out=self.work/'public'; self.backups=self.work/'backups'
        for name,visibility in [('a','public'),('b','her'),('c','private')]:
            (self.vault/(name+'.md')).write_text('---\nvisibility: '+visibility+'\n---\n'+name+' content',encoding='utf-8')

    def publish(self,apply=False):
        return pub.publish(self.vault,self.her,self.out,self.backups,apply=apply)

    def test_social_sections(self):
        value=loader.load_persona(self.her,target='social')
        for token in ('synthetic persona','synthetic voice','identity','principle','示例50','friendly phrase'):
            self.assertIn(token,value)
        self.assertNotIn('OWNER_ONLY_SENTINEL',value); self.assertNotIn('待批',value)

    def test_social_does_not_read_owner_sources(self):
        original=Path.read_text
        def read(path,*a,**kw):
            self.assertNotEqual(path.name,'relationship.md')
            self.assertNotEqual(path.name,'pending.json')
            return original(path,*a,**kw)
        with patch.object(Path,'read_text',read):
            loader.load_persona(self.her,target='social')

    def test_local_still_contains_relationship_pending(self):
        text=loader.load_persona(self.her)
        self.assertIn('OWNER_ONLY_SENTINEL',text); self.assertIn('待批',text)

    def test_social_hash_ignores_private_changes(self):
        old=loader.load_persona(self.her,target='social')
        (self.her/'relationship.md').write_text('CHANGED',encoding='utf-8')
        self.assertEqual(old,loader.load_persona(self.her,target='social'))
        (self.her/'voice.md').write_text('new voice',encoding='utf-8')
        self.assertNotEqual(old,loader.load_persona(self.her,target='social'))

    def test_default_zero_writes(self):
        result=self.publish()
        self.assertEqual(result['public_notes'],1)
        self.assertFalse(self.out.exists()); self.assertFalse(self.backups.exists())

    def test_apply_only_public(self):
        self.publish(True)
        self.assertTrue((self.out/'vault/a.md').exists())
        self.assertFalse((self.out/'vault/b.md').exists()); self.assertFalse((self.out/'vault/c.md').exists())
        self.assertNotIn('OWNER_ONLY_SENTINEL',(self.out/'persona-social.txt').read_text(encoding='utf-8'))

    def test_idempotent_zero_writes(self):
        self.publish(True)
        before={str(p):p.stat().st_mtime_ns for p in self.out.rglob('*') if p.is_file()}
        self.assertEqual(self.publish(True)['write'],0)
        self.assertEqual(before,{str(p):p.stat().st_mtime_ns for p in self.out.rglob('*') if p.is_file()})

    def test_revoked_note_moves_outside_public_without_deletion(self):
        self.publish(True)
        original=(self.out/'vault/a.md').read_bytes()
        (self.vault/'a.md').write_text('---\nvisibility: private\n---\nrevoked',encoding='utf-8')
        result=self.publish(True)
        self.assertEqual(result['withdraw'],1); self.assertFalse((self.out/'vault/a.md').exists())
        self.assertTrue(any(p.read_bytes()==original for p in self.backups.rglob('a.md')))

    def test_external_destination_change_aborts(self):
        self.publish(True); (self.out/'vault/a.md').write_text('external')
        with self.assertRaisesRegex(ValueError,'externally'): self.publish(True)

    def test_unmanaged_destination_aborts(self):
        self.out.mkdir(); (self.out/'private.txt').write_text('do not touch')
        with self.assertRaisesRegex(ValueError,'unmanaged'): self.publish(True)

    def test_overlapping_destination_rejected(self):
        with self.assertRaises(ValueError): pub.publish(self.vault,self.her,self.vault/'public',self.backups,apply=True)

    def test_invalid_frontmatter_aborts(self):
        (self.vault/'bad.md').write_text('---\nvisibility: public\n',encoding='utf-8')
        with self.assertRaises(ValueError): self.publish(True)
        self.assertFalse(self.out.exists())

    def test_social_limit_trims_expressions(self):
        (self.her/'evolution/expressions.md').write_text('\n'.join('- '+str(i)+'x'*150 for i in range(30)),encoding='utf-8')
        content=loader.load_persona(self.her,target='social',max_chars=1200)
        self.assertLessEqual(len(loader.render_persona(content,'social',self.her)),1200)
        self.assertIn('identity',content)

    def test_core_cannot_be_truncated(self):
        (self.her/'persona.md').write_text('core'*1000,encoding='utf-8')
        with self.assertRaises(ValueError): loader.load_persona(self.her,target='social',max_chars=900)

    def test_empty_optional_social_sections(self):
        bare=self.work/'bare'; bare.mkdir()
        (bare/'persona.md').write_text('- synthetic',encoding='utf-8')
        (bare/'voice.md').write_text('- voice',encoding='utf-8')
        value=loader.load_persona(bare,target='social')
        self.assertNotIn('## 底线',value); self.assertNotIn('## 当前性格参数',value)

    def test_hash_footer_covers_social_content(self):
        import hashlib
        content=loader.load_persona(self.her,target='social')
        expected=hashlib.sha256(content.encode()).hexdigest()[:8]
        self.assertIn('sha256='+expected,loader.render_persona(content,'social',self.her))

    def test_duplicate_visibility_rejected(self):
        (self.vault/'bad.md').write_text('---\nvisibility: private\nvisibility: public\n---\nsynthetic',encoding='utf-8')
        with self.assertRaises(ValueError): self.publish(True)

    def test_social_render_rejects_owner_content(self):
        local=loader.load_persona(self.her)
        with self.assertRaises(ValueError): loader.render_persona(local,'social',self.her)


if __name__=='__main__':
    unittest.main()
