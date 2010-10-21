def chopLine(line, maxLen):
	if len(line) <= maxLen: return (line, "")
	chopLoc = line[:maxLen+1].rfind(" ")
	if chopLoc > 0:
		return (line[:chopLoc], line[chopLoc+1:])
	else:
		return (line[:maxLen], line[maxLen:])

def ctrl(s): return curses.ascii.ctrl(ord(s))

import curses
import curses.ascii
import curses.textpad
import threading
import traceback

class ChatScreen(object):

	def __init__(self, screenInitCb, outboxCb):
		self.screenInitCb = screenInitCb
		self.outboxCb = outboxCb
		self.done = False
		self.cursesLock = threading.RLock()

	def cursesApp(self, stdscr):
		(maxY, maxX) = stdscr.getmaxyx()
		self.win1 = curses.newwin(maxY - 1, maxX, 0, 0)
		self.win2 = curses.newwin(1, maxX, maxY - 1, 0)
		self.win2.move(0, 0)
		self.textbox = curses.textpad.Textbox(self.win2)

		self.screenInitCb()

		while True:
			msg = self.textbox.edit(self.validate)
			try:
				self.outboxCb(msg)
			except: self.log(traceback.format_exc())
			with self.cursesLock:
				self.win2.deleteln()
				self.textbox.do_command(ctrl("A"))
			if self.done: return

	def validate(self, s):
		#self.log(repr(s))
		if s == ord("\n"): return ctrl("G")
		elif s == 127: return curses.KEY_BACKSPACE
		#elif s == curses.KEY_RIGHT:
		else: return s

	def log(self, msg, indent=0):
		(maxy, maxx) = self.win1.getmaxyx()
		assert indent < maxx - 1
		#indent = " " * indent
		if type(msg) is str: pass
		elif type(msg) is unicode: msg = msg.encode("ascii", "backslashreplace")
		else: msg = repr(msg)
		indentSpaces = " " * indent
		lines = []
		for line in msg.split("\n"):
			if not lines:
				(firstLine, line) = chopLine(line, maxx - 1)
				lines.append(firstLine)
			while line:
				(firstLine, line) = chopLine(line, maxx - 1 - indent)
				lines.append(indentSpaces + firstLine)
		with self.cursesLock:
			(y2, x2) = self.win2.getyx()
			(y1, x1) = self.win1.getyx()
			# probably fails if len(lines) > maxy
			nOverflow = y1 + len(lines) - maxy + 1
			if nOverflow:
				self.win1.move(0, 0)
				for i in range(nOverflow): self.win1.deleteln()
				self.win1.move(y1 - nOverflow, x1)
			for line in lines:
				self.win1.addstr(line + "\n")
			self.win1.refresh()
			self.win2.move(y2, x2)
			self.win2.refresh()

	def run(self):
		try: curses.wrapper(self.cursesApp)
		except KeyboardInterrupt: print "Interrupting curses"

	def stop(self):
		self.done = True

