"""Serial GUI verification with uncaught Qt-slot exceptions failed at teardown."""
import os
import sys
import traceback
from pathlib import Path
import pytest

os.environ['QT_QPA_PLATFORM'] = 'offscreen'

class SlotExceptionChecks:
    @pytest.fixture(autouse=True)
    def retained_slot_exceptions(self, request):
        errors = []
        previous = sys.excepthook
        def capture(kind, error, tb):
            message = ''.join(traceback.format_exception(kind, error, tb))
            errors.append(message)
            print('UNCAUGHT QT SLOT ' + request.node.nodeid + '\n' + message, flush=True)
        sys.excepthook = capture
        yield
        sys.excepthook = previous
        if errors:
            pytest.fail('Uncaught Qt-slot exception:\n' + '\n'.join(errors), pytrace=False)

arguments = sys.argv[1:]
if arguments and arguments[0] == "--batch":
    collection, start, end, label = arguments[1:]
    nodes = [line for line in Path(collection).read_text().splitlines() if "::" in line]
    arguments = ["-vv", *nodes[int(start):int(end)], "--timeout=120", "-o", "faulthandler_timeout=60", "--tb=short", "--junitxml", str(Path(__file__).parent / (label + ".xml"))]
raise SystemExit(pytest.main(arguments, plugins=[SlotExceptionChecks()]))
