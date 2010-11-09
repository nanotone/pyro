ECHO_MESSAGES = False

import json
import os
import sys

RCPATH = os.environ['HOME'] + "/.pyrorc"
try:
	settings = json.load(open(RCPATH))
	assert type(settings) is dict
except IOError:
	settings = {}
except:
	print "Existing file %s could not be loaded. Please fix it or delete it." % RCPATH
	sys.exit()
if 'groups' not in settings: settings['groups'] = {}



import urllib2
def setAuth(host, authToken):
	passwordMgr = urllib2.HTTPPasswordMgrWithDefaultRealm()
	passwordMgr.add_password(None, host, authToken, "X")
	handler = urllib2.HTTPBasicAuthHandler(passwordMgr)
	opener = urllib2.build_opener(handler)
	urllib2.install_opener(opener)
def getJson(url): return json.loads(urllib2.urlopen(host + url).read())
def postJson(url, data=None):
	data = json.dumps(data) if data else ""
	req = urllib2.Request(host + url, data)
	req.add_header('Content-Type', 'application/json')
	return urllib2.urlopen(req).read()


users = {}
def saveUser(userDict): users[userDict['id']] = userDict['name'] #"%s (%s)" % (user['name'], user['email_address'])



groupName = raw_input("Campfire group: ")
assert groupName.isalnum()
host = "https://%s.campfirenow.com" % groupName

selfUser = None
print "Getting user data..."
if groupName not in settings['groups']:
	authToken = raw_input("Never heard of it. Auth token? ")
	setAuth(host, authToken)
	try:
		selfUser = getJson("/users/me.json")['user']
	except urllib2.HTTPError: # be more specific, catch only 401s and 404s
		print "Couldn't sign in. Check your credentials and try again."
		sys.exit()
	settings['groups'][groupName] = authToken
	json.dump(settings, open(RCPATH, "w"), indent=2)
else:
	setAuth(host, settings['groups'][groupName])
	try:
		selfUser = getJson("/users/me.json")['user']
	except urllib2.HTTPError as httpError:
		if httpError.code == 401:
			print "Your saved credentials were not accepted. They shall be discarded."
			del settings['groups'][groupName]
			json.dump(settings, open(RCPATH, "w"), indent=2)
		else: print "Couldn't sign in. Try agin later?"
		sys.exit()
selfUserId = selfUser['id']
saveUser(selfUser)



print "Getting room list..."
rooms = getJson("/rooms.json")['rooms']
print "Rooms:"
for (index, room) in enumerate(rooms):
	print "%d: %s (%s), last updated %s" % (index, room['name'], room['topic'], room['updated_at'])
index = int(raw_input("Where would you like to go? "))
room = rooms[index]['id']



try:
	import Growl
	notifier = Growl.GrowlNotifier(applicationName="pyro", notifications=("msg",))
	notifier.register()
except ImportError:
	notifier = None

def notifyGrowl(username, body):
	if notifier: notifier.notify("msg", username, body)


def handleMsg(msg, notify=True): # expects a 37s json msg
	assert(type(msg is dict) and 'type' in msg)
	msgType = msg['type']
	if msgType in ("AdvertisementMessage", "TimestampMessage"): return
	line = ""
	indent = 0
	username = "Anonymous"
	if 'created_at' in msg: line += "%s " % msg['created_at'].split(" ")[1]
	if 'user_id' in msg:
		userId = msg['user_id']
		if type(userId) is int:
			if userId not in users:
				chat.log("Getting user data for %d" % userId)
				saveUser(getJson("/users/%d.json" % userId)['user'])
			username = users.get(userId, "Anonymous")
			line += "<%s>" % username
	if msgType == "TextMessage":
		indent = len(line) + 2
		line += ": %s" % msg['body']
		if notify and (ECHO_MESSAGES or msg.get('user_id') != selfUserId):
			notifyGrowl(username, msg['body'])
	elif msgType == "EnterMessage":
		line += " has entered the room."
	elif msgType == "KickMessage":
		line += " got kicked from the room."
		global joined
		if msg.get('user_id') == selfUserId: joined = False
		return
	elif msgType == "LeaveMessage":
		line += " has left the room."
	elif msgType == "UploadMessage":
		upload = getJson("/room/%s/messages/%d/upload.json" % (room, msg['id']))['upload']
		line += " uploaded %d bytes: %s" % (upload['byte_size'], upload['full_url'])
		if notify:
			notifyGrowl(username, "%s uploaded a file." % username)
	elif msgType == "PasteMessage":
		indent = len(line) + 9
		line += " pasted: %s" % msg['body']
		if notify:
			notifyGrowl(username, msg['body'])
	else:
		line += ": %r" % msg
	chat.log(line, indent)

################################################################################

import time
import traceback
import Queue
outbox = Queue.Queue()
done = False
def clamp(value, low, high): return min(max(value, low), high)

lastPing = 0

def handleOutgoing(msg):
	global joined, lastPing
	msg = msg.strip()
	if not msg: return
	if msg == "/who":
		roomUsers = getJson("/room/%s.json" % room)['room']['users']
		chat.log("Users currently in the room: " + ", ".join(u['name'] for u in roomUsers))
	else:
		if not joined: joinRoom()
		postJson("/room/%s/speak.json" % room, {'message': {'body': msg}})
	lastPing = 0 # force a ping


def runNetwork():
	chat.log("Joining room...")
	joinRoom()
	global done, lastPing
	pingInterval = 3
	since = 0
	while True:
		if done: return
		try:
			if time.time() - lastJoin > 180: joinRoom()
			try: handleOutgoing(outbox.get(True, clamp(lastPing + pingInterval - time.time(), 0, 1)))
			except Queue.Empty: pass
			if lastPing + pingInterval < time.time():
				url = "/room/%s/recent.json" % room
				if since: url += "?since_message_id=%d" % since
				try:
					msgs = getJson(url)['messages']
					#if since == 0: msgs = msgs[-49:] # limit massive chatdump upon signin?
					for msg in msgs: handleMsg(msg, notify=since)
					if msgs: since = msgs[-1]["id"]
					lastPing = time.time()
				except urllib2.HTTPError as httpError:
					chat.log("urllib2: HTTP %d %s" % (httpError.code, httpError.msg))
				except urllib2.URLError as urlError:
					if urlError.reason.errno in (8, 50, 54, 60):
						chat.log("urllib2: %s" % urlError.reason)
					else: raise
			time.sleep(0.1)
		except KeyboardInterrupt: break
		except: chat.log(traceback.format_exc())
	chat.stop()

def joinRoom():
	try:
		postJson("/room/%s/join.json" % room)
		global joined, lastJoin
		joined = True
		lastJoin = time.time()
	except urllib2.URLError: pass

def startNetwork():
	chat.log("Getting room data...")
	for user in getJson("/room/%s.json" % room)['room']['users']: saveUser(user)
	chat.log("Users currently in the room: " + (", ").join(users.values()) )
	global runNetworkThread
	import threading
	runNetworkThread = threading.Thread(group=None, target=runNetwork, name="Network-thread")
	runNetworkThread.start()

import chatscreen
chat = chatscreen.ChatScreen(startNetwork, outbox.put)
chat.run()
done = True
runNetworkThread.join()

if joined: postJson("/room/%s/leave.json" % room)
print "Bye now."

