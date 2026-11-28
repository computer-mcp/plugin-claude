import hashlib
import importlib.util
import io
import json
import re
import runpy
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
import tomllib
import unittest
from support import Client
import zipfile

ROOT=Path(__file__).resolve().parent.parent
spec=importlib.util.spec_from_file_location('build_package',ROOT/'scripts/build_package.py')
builder=importlib.util.module_from_spec(spec);spec.loader.exec_module(builder)

class PackageTests(unittest.TestCase):
    def test_reviewed_manifest_matches_actual_adapter_catalog(self):
        manifest=tomllib.loads((ROOT/'computer-mcp-plugin.toml').read_text())
        self.assertEqual(manifest['permissions'],[{
            'id':'project','access':'write',
            'purpose':'Run requested Claude Code tasks and edits in owner-selected project worktrees, and manage the executions this adapter owns.'}])
        sandbox = manifest['sandbox']
        self.assertEqual(set(sandbox), {'network', 'purpose'})
        self.assertEqual(sandbox['network'], {
            'level': 'custom',
            'hosts': ['api.anthropic.com', 'platform.claude.com', 'claude.ai'],
            'include_trusted': False,
        })
        mcp=manifest['mcp'][0]
        self.assertEqual(mcp['requirements'],{'project':'write'})
        self.assertEqual(mcp['tool_requirements'],{
            name:{'project':'read'} for name in
            ('claude.run.list','claude.run.result','claude.run.events')})
        with tempfile.TemporaryDirectory() as temp:
            client=Client(temp)
            try:
                catalog=client.request('tools/list')['result']['tools']
            finally:
                client.close()
        names={tool['name'] for tool in catalog}
        self.assertEqual(names,{'claude.run','claude.run.start','claude.run.list',
                              'claude.run.result','claude.run.events',
                              'claude.run.cancel','claude.run.release'})
        self.assertLessEqual(set(mcp['tool_requirements']),names)
        for tool in catalog:
            self.assertNotIn('requirements',tool.get('_meta',{}))
            required=mcp['tool_requirements'].get(tool['name'],mcp['requirements'])
            self.assertEqual(required['project'],
                             'read' if tool['annotations']['readOnlyHint'] else 'write')
        self.assertEqual([x['id'] for x in manifest['cli']],['claude'])
        self.assertEqual([x['id'] for x in manifest['skills']],['claude-code'])
        self.assertNotIn('host_service_contract',manifest)

    def test_reproducible_archive_and_executable_mode(self):
        first,manifest=builder.package_bytes(ROOT)
        self.assertEqual(first,builder.package_bytes(ROOT)[0])
        with zipfile.ZipFile(io.BytesIO(first)) as archive:
            names=archive.namelist()
            self.assertIn('computer-mcp-plugin.toml',names)
            self.assertIn('cli-tree.json',names)
            self.assertIn('bin/plugin_runtime.py',names)
            for asset in builder.README_ASSETS:
                self.assertIn(asset,names)
                self.assertEqual(archive.read(asset),(ROOT/asset).read_bytes())
            self.assertEqual({name for name in names if name.startswith('.github/')},
                             set(builder.README_ASSETS))
            packaged_manifest=tomllib.loads(archive.read('computer-mcp-plugin.toml').decode())
            self.assertIs(type(packaged_manifest['plugin_api']),int)
            self.assertEqual(packaged_manifest['plugin_api'],1)
            for entry in archive.infolist():
                if entry.filename not in builder.README_ASSETS:
                    self.assertFalse(any(p.startswith('.') for p in Path(entry.filename).parts))
                self.assertNotIn('__pycache__',Path(entry.filename).parts)
                self.assertFalse(entry.filename.endswith(('.pyc','.pyo')))
                expected=0o755 if entry.filename in (
                    "bin/claude-mcp-adapter", "bin/claude-mcp-managed") else 0o644
                self.assertEqual(stat.S_IMODE(entry.external_attr>>16),expected)
            with tempfile.TemporaryDirectory() as temp:
                archive.extractall(temp)
                command=[sys.executable,str(Path(temp)/f"bin/{manifest['id']}-mcp-adapter"),'--version']
                result=subprocess.run(command,capture_output=True,text=True,timeout=3)
                self.assertEqual(result.returncode,0,result.stderr)
                self.assertEqual(result.stdout.strip(),manifest['version'])
    def test_managed_inventory_binds_both_entrypoints_and_the_reviewed_print_recipe(self):
        data, manifest = builder.package_bytes(ROOT)
        mcp = manifest['mcp'][0]
        self.assertEqual(mcp['executable'], {'path': 'bin/claude-mcp-managed'})
        declaration = mcp['vendor_execution']
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            signature = json.loads(archive.read(declaration['signature']))
            self.assertEqual(set(declaration['files']), {
                'claude-vendor-execution.json', 'bin/claude-mcp-adapter',
                'bin/claude-mcp-managed', 'bin/claude_vendor_execution.py',
                'bin/plugin_runtime.py', 'cli-tree.json',
            })
            for path, digest in declaration['files'].items():
                self.assertEqual(hashlib.sha256(archive.read(path)).hexdigest(), digest, path)
        self.assertEqual(signature['dependency'], declaration['dependency'])
        self.assertEqual(signature['tools'], {
            'claude.run': 'acquire', 'claude.run.start': 'detached_acquire',
            'claude.run.list': 'observe', 'claude.run.result': 'observe',
            'claude.run.events': 'observe', 'claude.run.cancel': 'close',
            'claude.run.release': 'observe',
        })
        self.assertEqual(signature['workload']['kind'], 'print')
        sys.path.insert(0, str(ROOT / 'bin'))
        try:
            adapter = runpy.run_path(str(ROOT / 'bin/claude-mcp-adapter'))
        finally:
            sys.path.pop(0)
        self.assertEqual(signature['probe'], ['--version'])
        self.assertEqual(signature['version_stdout'], adapter['expected_version'](adapter['TREE']))
        cases = (
            {'prompt': "--leading 'quotes' 中文\nnext"},
            {'prompt': 'all scalar options', 'permission_mode': 'plan', 'model': 'offline',
             'resume_session_id': 'existing-session', 'max_budget_usd': 2.5,
             'effort': 'high', 'append_system_prompt': '--literal'},
            {'prompt': 'new session', 'no_session_persistence': True,
             'session_id': '12345678-1234-4234-9234-123456789012'},
            {'prompt': 'continue', 'continue_previous': True},
        )
        for arguments in cases:
            argv = []
            for token in signature['workload']['argv']:
                kind = token['kind']
                if kind == 'literal':
                    argv.append(token['value'])
                    continue
                value = arguments.get(token['parameter'], token.get('default'))
                if kind == 'positional':
                    argv.append(value)
                elif kind == 'flag' and value:
                    argv.append(token['flag'])
                elif kind == 'option' and value is not None:
                    if token['style'] == 'separate':
                        argv.extend([token['flag'], str(value)])
                    else:
                        argv.append(token['flag'] + '=' + str(value))
            self.assertEqual(argv, adapter['build_command']('fixture', arguments)[0][1:])

    def test_readme_relative_links_resolve_in_archive(self):
        data,_=builder.package_bytes(ROOT)
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            readme=archive.read('README.md').decode()
            links=re.findall(r'(?:href|src|srcset)="([^"]+)"|\]\(([^)]+)\)',readme)
            for html,markdown in links:
                target=(html or markdown).split('#',1)[0]
                if target and '://' not in target:
                    self.assertIn(target,archive.namelist())

    def test_bytecode_and_local_metadata_cannot_change_release_bytes(self):
        before,_=builder.package_bytes(ROOT)
        with tempfile.TemporaryDirectory() as temp:
            copy=Path(temp)/'source';copy.mkdir()
            for name in builder.INCLUDE:
                source=ROOT/name
                if source.is_dir():shutil.copytree(source,copy/name)
                else:
                    (copy/name).parent.mkdir(parents=True,exist_ok=True)
                    shutil.copyfile(source,copy/name)
            (copy/'.github/assets/logo/unlisted.png').write_bytes(b'not-release-content')
            cache=copy/'bin/__pycache__';cache.mkdir(exist_ok=True)
            (cache/'arbitrary.pyc').write_bytes(b'not-release-content')
            (copy/'bin/.DS_Store').write_bytes(b'not-release-content')
            self.assertEqual(before,builder.package_bytes(copy)[0])
    def test_cli_prompt_mapping_has_an_explicit_option_separator(self):
        tree=json.loads((ROOT/'cli-tree.json').read_text())
        for command in tree['commands']:
            tokens=command.get('argv',[])
            position=next((i for i,x in enumerate(tokens) if x.get('parameter')=='prompt'),None)
            if position is not None:
                self.assertEqual(tokens[position-1],{'kind':'literal','value':'--'})

if __name__=='__main__':unittest.main()
