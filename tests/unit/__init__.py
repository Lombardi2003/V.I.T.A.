# V.I.T.A. unit tests (unittest, nothing to install).
#
# Real graph, fake model: each test decides what the model "answers" and checks
# what the system does (who speaks, what appears in the chat, what ends up in
# the state). They use no API quota and say nothing about the model's clinical
# quality - for that, see the live scripts in tests/live/.
#
# Usage, from the project folder:
#     python -m tests.run unit
