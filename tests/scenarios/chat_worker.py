"""Subprocess fixture: real employee database and worker authorization, fake model."""
import sys
from unittest.mock import patch

import django
django.setup()
from leadzen.chat.engine import Decision, drive

with patch("leadzen.chat.engine.decide", side_effect=[Decision(tool="overview"), Decision(tool="answer", text="Synthetic isolated worker completed")]):
    drive(sys.argv[1])
