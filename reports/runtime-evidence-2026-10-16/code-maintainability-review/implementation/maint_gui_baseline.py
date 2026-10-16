"""Load pre-maintenance GUI adapters in-memory; do not revert shared files."""
import importlib.abc
import importlib.util
from pathlib import Path
import subprocess
import sys

repo=Path.cwd()
overrides={
    name:subprocess.check_output(['git','show',f'HEAD:src/{name.replace(".","/")}.py'],text=True)
    for name in ('cephvr.gui.epoch_selection','cephvr.gui.stimulus_columns','cephvr.gui.managed_display_operations')
}
overrides['cephvr.gui.controller_bridge']=Path('/tmp/controller_bridge.before.py').read_text()

class Before(importlib.abc.MetaPathFinder,importlib.abc.Loader):
    def find_spec(self,fullname,path=None,target=None):
        if fullname in overrides:
            return importlib.util.spec_from_loader(fullname,self,origin=str(repo/'src'/f'{fullname.replace(".","/")}.py'))
    def create_module(self,spec):
        return None
    def exec_module(self,module):
        exec(compile(overrides[module.__name__],module.__spec__.origin,'exec'),module.__dict__)

sys.meta_path.insert(0,Before())
import pytest
raise SystemExit(pytest.main(['tests/gui/test_dashboard.py','-q','-k','test_trial_row_actions_scroll_target_and_align_cards']))
