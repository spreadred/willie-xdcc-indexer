'''
Created on Feb 23, 2014

@author: Rohn Adams
'''

import re
from willie.module import rule, event, priority, commands
from willie.config import ConfigurationError

# removes packs #s that are supposedly no longer served
# but have not been replaced by another pack
def deleteExcessPacks(c, botNick, maxPacks):
    # bullshit vars
    if(botNick is None) or (maxPacks < 0) or (c is None):
        return 0
    
    return c.execute("DELETE FROM packs WHERE botnick = %s AND number > %s", (botNick, int(maxPacks)))
        
# use decorator to set up xsearch command
# TODO: can this be done inside a class?
@commands("xsearch")
def packSearch(bot, trigger):
    
    # split out our search terms
    searchterms = trigger.args[1].split()
    
    termsLength = len(searchterms)
    
    if(termsLength < 2): # didn't submit any terms
        bot.debug(__file__, "No search terms submitted", "warning")
        bot.msg(trigger.nick, "No search terms submitted")
        return 0
    
    # TODO: protect against short and common words?
    
    # open up db connection
    # TODO: try/catch any errors?
    conn = bot.db.connect()
    
    with conn:
        c = conn.cursor()
        
        # parse our search terms
        searchline = "%" # match everything, should protect against this
            
        for i in range(1,termsLength):
            # term must be 3 letters or more
            if(len(searchterms[i]) > 2):
                searchline += (searchterms[i] + "%")
            else:
                bot.debug(__file__, "Threw away short search term: " + searchterms[i], "verbose")
                
        # check searchline to make sure we came up with something valid
        if(len(searchline) < 2): # account for the %
            bot.debug(__file__, "No valid search terms, probably all were short.", "warning")
            bot.msg(trigger.nick, "No valid search terms submitted. Terms must be 3 letters or more.")
            return 0
        
        bot.debug(__file__, "Searching index for: " + searchline, "verbose")
        
        # TODO: set a limit of rows to retrieve, determine a decent value
        # TODO: notify user if more packs exist, tell them to be more specific
        
        c.execute("SELECT * FROM packs WHERE description LIKE %s ORDER BY description LIMIT 30", (searchline))
        
        # read all rows into memory, as db size increases maybe switch to iterations
        rows = c.fetchall()
        
        # let them know how many matches were found
        bot.msg(trigger.nick, "Found {} possible matches for your search:".format(len(rows)))
        
        for row in rows:
            # create xdccPack, kinda pointless at this point oh well
            pack = xdccPack(row[2], row[3], row[4], row[5])
            
            # attempt to retrieve matching bot information            
            c.execute("SELECT * FROM bots WHERE nick = %s LIMIT 1", (row[1],))
             
            botrow = c.fetchone()
            if botrow is not None:
                currentBot = xdccBot(botrow[1], botrow[2], botrow[3], botrow[4], botrow[5], botrow[6], 
                                     botrow[7], botrow[8], botrow[9], botrow[10], 
                                     botrow[11], botrow[12])
                bot.msg(trigger.nick, "Pack #{} - {} - Size: {} - Gets: {} - Command: {} #{}".format
                        (pack.number, pack.description, pack.size, pack.gets, currentBot.request_command, pack.number))
            
       
# gotta grab every message so we can strip out control codes.      
@event('PRIVMSG')
@rule('.*')
@priority('high')
def on_message(bot, trigger):
    # fucking bullshit, i hate you control codes
    # strip m(IRC) control codes, hopefully
    # TODO: strip that pesky unicode 2026 or wtfever
    fuckunicode = re.compile(ur'\u2026', re.UNICODE)
    
    result = fuckunicode.sub('...', trigger.bytes)
    regex = re.compile(r"\x1f|\x02|\x12|\x0f|\x16|\x03(?:\d{1,2}(?:,\d{1,2})?)?", re.UNICODE)
    stripped = regex.sub("", result)
    
    parseLine(stripped, bot, trigger)

def parseLine(stripped, bot, trigger):
    # TODO: classify and member function all these little bitches
    
    # check if line is an actual pack description line
    # this is most common, so check first for efficiency
    match = re.search('(?i)#(\d+)\s+(\d+)x\s+\[(\s*\d+\.?\d+\S)\]\s+(.*)', stripped)
    
    if match:
        parsePackLine(bot, trigger, match)
        return 
    
    # check for a stop listing line, these aren't very common
    match = re.search('(?i)\*\*\s+To\s+stop\s+this\s+listing,\s+type\s+\"(/.*)\"', stripped)
    
    if match:
        parseStopListingLine(bot, trigger, match)
        return
    
    # check for a packs/slots/record line
    match = re.search('(?i)\*\*\s+(\d+)\s+packs\s+\*\*\s+(\d+)\s+of\s+(\d+)\s+slots\s+open', stripped)
    
    if match:
        parsePacksSlotsRecordLine(bot, trigger, match, stripped)
        return
    
    # check for bandwidth usage line    
    match = re.search('(?i)\*\*\s+Bandwidth\s+Usage\s+\*\*\s+Current:\s+(\d+\.\d+\S+),', stripped) 
    
    if match:
        parseBandwidthUsageLine(bot, trigger, match, stripped)
        return 
    
    # check for request command line
    match = re.search('(?i)\*\*\s+To\s+request\s+a\s+file,\s+type\s+\"(.*)x\".*', stripped)
    
    if match:
        parseRequestLine(bot, trigger, match)
        return
    
    match = re.search('\*\*\s+To\s+request\s+details,\s+type\s+\"(.*)\".*', stripped)
    
    # check for details command line, rarely used
    if match:
        parseDetailsLine(bot, trigger, match)
        return
    
    # check for total offered line
    match = re.search('(?i)Total\s+Offered:\s+(\d+\S+)\s+Total\s+Transferred:\s+(\d+\S+)', stripped)
    
    if match:
        parseTotalOfferedLine(bot, trigger, match)
        return;

def setup(bot):
   
    if not bot.db:
        raise ConfigurationError("Database not set up, or unavailable.")
    
    # connect bot's database
    conn = bot.db.connect()
    
    with conn:
        c = conn.cursor()
        
        # create needed tables, if not already existing
        # this tosses warnings, maybe not the best way to do this
        create_bots_table(c)
        create_packs_table(c)
        conn.commit()
            
 
# create a packs table if not exists       
def create_packs_table(c):    
    c.execute("CREATE TABLE IF NOT EXISTS packs (id INTEGER NOT NULL AUTO_INCREMENT PRIMARY KEY, "
        "botnick TEXT, "
        "number INTEGER, "
        "gets INTEGER, "
        "size TEXT, "
        "description TEXT, "
        "filename TEXT, "
        "filesize INTEGER, "
        "last_modified INTEGER, "
        "md5sum BLOB, "
        "crc32 BLOB, "
        "added INTEGER)")

# create a bots table it not exists   
def create_bots_table(c):
    c.execute("CREATE TABLE IF NOT EXISTS bots "
        "(id INTEGER NOT NULL AUTO_INCREMENT PRIMARY KEY, "
        "nick TEXT, "
        "requestcommand TEXT, "
        "detailscommand TEXT, "
        "stopcommand TEXT, "
        "numpacks INTEGER, "
        "totalslots INTEGER, "
        "availableslots INTEGER, "
        "currentbandwidth TEXT, "
        "recordbandwidth TEXT, "
        "recordtotalbandwidth TEXT, "
        "totaloffered TEXT, "
        "totaltransferred TEXT)")
    
def checkBotDBEntryExists(c, nick):
    c.execute("""SELECT 1 FROM bots WHERE nick = %s""", (nick))
    
    if c.fetchone() is None:
        return False
    else:
        return True
        

#@rule('(?i)\*\*\s+To\s+stop\s+this\s+listing,\s+type\s+\"(/.*)\"')        
def parseStopListingLine(bot, trigger, match):
    'Attempts to parse a stop listing line from a xdcc bot'  
    #** To stop this listing, type "/MSG Liquid-xdcc-Bot XDCC STOP"
    # 
    # 
    stop_command = match.group(1)
    
    # put it in the database
    conn = bot.db.connect()
    
    with conn:
        c = conn.cursor()
                     
        if not checkBotDBEntryExists(c, trigger.nick):
            c.execute('''
                INSERT INTO bots (nick, stopcommand) VALUES (%s, %s)
                ''', (trigger.nick, stop_command))
        else:
            c.execute('''
                UPDATE bots SET stop_command = %s
                WHERE nick = %s
                ''', (stop_command, trigger.nick))
        
  
        
#@rule('(?i)\*\*\s+(\d+)\s+packs\s+\*\*\s+(\d+)\s+of\s+(\d+)\s+slots\s+open,\s+record:\s+(\d+\.\d+\S+/s)')
def parsePacksSlotsRecordLine(bot, trigger, match, stripped):
    'Attempts to parse a packs, slots, record line'
    #** 201 packs **  99 of 100 slots open, Record: 74874.0kB/s
    
    conn = bot.db.connect()
    
    with conn:
        c = conn.cursor()
        
        numpacks = match.group(1)
        availableslots = match.group(2)
        totalslots = match.group(3)
        
        bandwidth = re.search('(?i)record:\s+(\d+\.\d+\S+/s)', stripped)
        
        if bandwidth:
            recordtotalbandwidth = bandwidth.group(1)
        else:
            recordtotalbandwidth = ""
        
        if not checkBotDBEntryExists(c, trigger.nick):
            c.execute('''
                INSERT INTO bots (nick, numpacks, availableslots, totalslots, recordtotalbandwidth) VALUES (%s, %s, %s, %s, %s)
                ''', (trigger.nick, int(numpacks), int(availableslots), int(totalslots), recordtotalbandwidth))
        else:
            c.execute('''
                UPDATE bots SET numpacks = %s, availableslots = %s, totalslots = %s, recordtotalbandwidth = %s WHERE nick = %s
                ''', (int(numpacks), int(availableslots), int(totalslots), recordtotalbandwidth, trigger.nick))
            # clear out any excess packs
            deleteExcessPacks(c, trigger.nick, numpacks)
        conn.commit()
          
    
#@rule('(?i)\*\*\s+Bandwidth\s+Usage\s+\*\*\s+Current:\s+(\d+\.\d+\S+),\s+record:\s+(\d+\.\d+\S+/s)')
def parseBandwidthUsageLine(bot, trigger, match, stripped):
    'Attempts to parse a bandwidth usage line'
    #** Bandwidth Usage ** Current: 0.0kB/s, Record: 15408.5kB/s
    
    conn = bot.db.connect()
    
    with conn:
        c = conn.cursor()
        
        currentbandwidth = match.group(1)
        
        record = re.search('(?i)record:\s+(\d+\.\d+\S+/s)', stripped)
        
        if record:
            recordbandwidth = match.group(1)
        else:
            recordbandwidth = ""
        
        if not checkBotDBEntryExists(c, trigger.nick):
            c.execute('''
                INSERT INTO bots (nick, currentbandwidth, recordbandwidth) VALUES (%s, %s, %s)
                ''', (trigger.nick, currentbandwidth, recordbandwidth))
        else:
            c.execute('''
                UPDATE bots SET currentbandwidth = %s, recordbandwidth = %s WHERE nick = %s
                ''', (currentbandwidth, recordbandwidth, trigger.nick))

#@rule('(?i)\*\*\s+To\s+request\s+a\s+file,\s+type\s+\"(.*)\".*')    
def parseRequestLine(bot, trigger, match):
    'Attempts to parse a request command line'
    # ** To request a file, type "/MSG Liquid-xdcc-Bot XDCC SEND x" **
    # TODO: maybe allow other commands besides send or get?
    # TODO: allow others besides x
    conn = bot.db.connect()
    
    with conn:
        c = conn.cursor()
        
        requestcommand = match.group(1)
            
        if not checkBotDBEntryExists(c, trigger.nick):
            c.execute('''
                INSERT INTO bots (nick, requestcommand) VALUES (%s, %s)
                ''', (trigger.nick, requestcommand))
        else:
            c.execute('''
                UPDATE bots SET requestcommand = %s WHERE nick = %s
                ''', (requestcommand, trigger.nick))
        conn.commit()
        
   
#@rule('\*\*\s+To\s+request\s+details,\s+type\s+\"(.*)\".*') 
def parseDetailsLine(bot, trigger, match):
    conn = bot.db.connect()
    
    with conn:
        c = conn.cursor()
        
        detailscommand = match.group(1)
        
        if not checkBotDBEntryExists(c, trigger.nick):
            c.execute('''
                INSERT INTO bots (nick, detailscommand) VALUES (%s, %s)
                ''', (trigger.nick, detailscommand))
        else:
            c.execute('''
                UPDATE bots SET detailscommand = %s WHERE nick = %s
                ''', (detailscommand, trigger.nick))
        conn.commit()
        

def checkPackDBEntryExists(c, nick, number):
    c.execute('''
        SELECT 1 FROM packs WHERE botnick = %s AND number = %s
        ''', (nick, int(number)))
    
    if c.fetchone() is None:
        return False
    else:
        return True
    
#@rule('(?i)#(\d+)\s+(\d+)x\s+\[(\s*\d+\.?\d+\S)\]\s+(.*)')    
def parsePackLine(bot, trigger, match):
    conn = bot.db.connect()
    
    with conn:
        c = conn.cursor()
            
        pack = xdccPack(match.group(1), match.group(2), match.group(3), match.group(4))
        
        if not checkPackDBEntryExists(c, trigger.nick, pack.number):
            c.execute('''
                INSERT INTO packs (botnick, number, gets, size, description) VALUES (%s, %s, %s, %s, %s)
                ''', (trigger.nick, int(pack.number), int(pack.gets), pack.size, pack.description))
        else:
            c.execute('''
                UPDATE packs SET gets = %s, size = %s, description = %s WHERE botnick = %s AND number = %s
                ''', (int(pack.gets), pack.size, pack.description, trigger.nick, int(pack.number)))
        
        conn.commit()
        
    
#@rule('(?i)Total\s+Offered:\s+(\d+\S+)\s+Total\s+Transferred:\s+(\d+\S+)')    
def parseTotalOfferedLine(bot, trigger, match):
    'Attempts to parse a total offered line'
    # Total Offered: 416GB  Total Transferred: 525GB
    conn = bot.db.connect()
    
    with conn:
        c = conn.cursor()
        
        totaloffered = match.group(1)
        totaltransferred = match.group(2)
     
        if not checkBotDBEntryExists(c, trigger.nick):
            c.execute('''
                INSERT INTO bots (nick, totaloffered, totaltransferred) VALUES (%s, %s, %s)
                ''', (trigger.nick, totaloffered, totaltransferred))
        else:
            c.execute('''
                UPDATE bots SET totaloffered = %s, totaltransferred = %s WHERE nick = %s
                ''', (totaloffered, totaltransferred, trigger.nick))
        conn.commit()
        
    
class xdccPack:
    'Represents an iroffer XDCC pack'
    def __init__(self, number=None, gets=0, size=None, description=None):
        self.number = number
        self.gets = gets
        self.size = size # string representation of size, eg: 1.5G or 14M
        self.description = description # description of pack
        
        #xdcc info details (currently UNUSED) - requesting details on each pack seems pointless
        # most would have it disabled anyway
        self.filename = None
        self.filesize = 0
        self.last_modified = None
        self.md5sum = None
        self.crc32 = None
        
class xdccBot:
    'Represents an iroffer XDCC bot'
    def __init__(self, nick=None, request_command=None, details_command=None, stop_command=None, numPacks=0, totalSlots=0, availableSlots=0, 
                 currentBandwidth=None, recordBandwidth=None, recordTotalBandwidth=None, totalOffered=0, totalTransferred=0, packs=[]):
        self.nick = nick
        self.request_command = request_command
        self.details_command = details_command # pointless, unused
        self.stop_command = stop_command # pointless, unused
        self.numPacks = numPacks
        self.totalSlots = totalSlots
        self.availableSlots = availableSlots
        self.currentBandwidth = currentBandwidth
        self.recordBandwidth = recordBandwidth
        self.recordTotalBandwidth = recordTotalBandwidth
        self.totalOffered = totalOffered
        self.totalTransferred = totalTransferred
        self.packs = packs # list of packs bot has of type xdccPack   