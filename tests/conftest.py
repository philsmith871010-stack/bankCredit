"""All tests share one scratch data directory, set before any bankcredit import, so the repo's data/ is never touched."""
import os, tempfile
os.environ["BANKCREDIT_DATA"] = os.environ.get("BANKCREDIT_TEST_DATA") or tempfile.mkdtemp(prefix="counterparty-tests-")
