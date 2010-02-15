#!/usr/bin/env python
# Copyright 2010, Brian Taylor
# Distribute under the terms of the GNU General Public License
# Version 2 or better


# this file contains the configurable variables
config_file = "config.ini"

# main webapp
import os
import re
import web
from PyRSS2Gen import *
import eyeD3
import urllib
import ConfigParser
import common

class RSSImageItem(RSSItem):
  "extending rss items to support our extended tags"
  TAGS = ('image', 'filetype', 'tracknum')
  def __init__(self, **kwargs):
    for name in RSSImageItem.TAGS:
      if name in kwargs:
        setattr(self, name, kwargs[name])
        del kwargs[name]
      else:
        setattr(self, name, None)

    RSSItem.__init__(self, **kwargs)

  def publish_extensions(self, handler):
    for name in RSSImageItem.TAGS:
      val = getattr(self, name)
      if val:
        handler.startElement(name, {})
        handler.characters(val)
        handler.endElement(name)

def file2item(fname, config, image=None):
  # guess the filetype based on the extension
  ext = os.path.splitext(fname)[1].lower()

  title = "None"
  description = "None"
  filetype = None
  mimetype = None
  tracknum = None

  if ext == ".mp3":
    # use the ID3 tags to fill out the mp3 data

    try:
      tag = eyeD3.Tag()
      if not tag.link(fname):
        return None
    except:
      print "library failed to parse ID3 tags for %s. Skipping." % fname
      return None

    title = tag.getTitle()
    description = tag.getArtist()
    
    tracknum = tag.getTrackNum()[0]
    if tracknum:
      tracknum = str(tracknum)


    filetype = "mp3"
    mimetype = "audio/mpeg"

  elif ext == ".wma":
    # use the filename as the title

    basename = os.path.split(fname)[1]
    title = os.path.splitext(basename)[0]
    description = ""
    filetype = "wma"
    mimetype = "audio/x-ms-wma"

  elif ext == ".m4v":
    # this is a video file

    basename = os.path.split(fname)[1]
    title = os.path.splitext(basename)[0]
    description = "Video"
    filetype = "mp4"
    mimetype = "video/mp4"

  else:
    # don't know what this is

    return None

  size = os.stat(fname).st_size
  link="%s/media?%s" % (common.server_base(config), urllib.urlencode({'name':to_utf8(fname)}))

  if image:
    image = "%s/image?%s" % (common.server_base(config), urllib.urlencode({'name':to_utf8(image)}))

  print link

  return RSSImageItem(
      title = title,
      link = link,
      enclosure = Enclosure(
        url = link,
        length = size,
        type = mimetype),
      description = description,
      guid = Guid(link, isPermaLink=0),
      pubDate = datetime.datetime.now(),
      image = image,
      filetype = filetype,
      tracknum = tracknum)

def dir2item(dname, config, image):
  link = "%s/feed?%s" % (common.server_base(config), urllib.urlencode({'dir':to_utf8(dname)}))
  name = os.path.split(dname)[1]

  if image:
    image = "%s/image?%s" % (common.server_base(config), urllib.urlencode({'name':to_utf8(image)}))

  description = "Folder"
  #if image:
  #  description += "<img src=\"%s\" />" % image

  return RSSImageItem(
      title = name,
      link = link,
      description = description,
      guid = Guid(link, isPermaLink=0),
      pubDate = datetime.datetime.now(),
      image = image)

def getart(path):
  curr_image = None
  img_re = re.compile(".jpg|.jpeg|.png")

  for base, dirs, files in os.walk(path):
    # don't recurse when searching for artwork
    del dirs[:]

    for file in files:
      ext = os.path.splitext(file)[1]
      if ext and img_re.match(ext):
        curr_image = os.path.join(base,file)
        break

  return curr_image

def to_unicode(obj, encoding='utf-8'):
  "convert to unicode if not already and it's possible to do so"

  if isinstance(obj, basestring):
    if not isinstance(obj, unicode):
      obj = unicode(obj, encoding)
  return obj

def to_utf8(obj):
  "convert back to utf-8 if we're in unicode"

  if isinstance(obj, unicode):
    obj = obj.encode('utf-8')
  return obj

def item_sorter(lhs, rhs):
  # folders always come before non folders
  if lhs.description == "Folder" and rhs.description != "Folder":
    return -1
  if rhs.description == "Folder" and lhs.description != "Folder":
    return 1

  # first sort by artist
  if lhs.description.lower() < rhs.description.lower():
    return -1
  if rhs.description.lower() < lhs.description.lower():
    return 1

  # things with track numbers always come first
  if lhs.tracknum and not rhs.tracknum:
    return -1
  if rhs.tracknum and not lhs.tracknum:
    return 1

  # if both have a track number, sort on that
  if lhs.tracknum and rhs.tracknum:
    if int(lhs.tracknum) < int(rhs.tracknum):
      return -1
    elif int(lhs.tracknum) > int(rhs.tracknum):
      return 1
  
  # if the track numbers are the same or both don't
  # exist then sort by title
  if lhs.title.lower() < rhs.title.lower():
    return -1
  elif rhs.title.lower() < lhs.title.lower():
    return 1
  else:
    return 0 # they must be the same

def getdoc(path, config, recurse=False):
  "get a media feed document for path"

  # make sure we're unicode
  path = to_unicode(path)

  items = []
  media_re = re.compile("\.mp3|\.wma|\.m4v")

  for base, dirs, files in os.walk(path):
    if not recurse:
      for dir in dirs:
        subdir = os.path.join(base,dir)
        items.append(dir2item(subdir, config, getart(subdir)))

      del dirs[:]

    # first pass to find images
    curr_image = getart(base)

    for file in files:
      if not media_re.match(os.path.splitext(file)[1].lower()):
        print "rejecting %s" % file
        continue
      
      item = file2item(os.path.join(base,file), config, curr_image)
      if item:
        items.append(item)

  # sort the items
  items.sort(item_sorter)

  doc = RSS2(
      title="A Personal Music Feed",
      link="%s/feed?dir=%s" % (common.server_base(config), path),
      description="My music.",
      lastBuildDate=datetime.datetime.now(),
      items = items )

  return doc

def doc2m3u(doc):
  "convert an rss feed document into an m3u playlist"

  lines = []
  for item in doc.items:
    lines.append(item.link)
  return "\n".join(lines)

def get_entropy(entries):
  "return an xml document full of random numbers since roku can't make them itself"
  import xml.dom.minidom as dom
  import random

  impl = dom.getDOMImplementation()
  doc = impl.createDocument(None, "entropy", None)
  top = doc.documentElement

  for ii in range(entries):
    el = dom.Element("entry")
    el.setAttribute("value", str(random.randrange(0,1000000)))
    top.appendChild(el)

  return doc

def range_handler(fname):
  "return all or part of the bytes of a fyle depending on whether we were called with the HTTP_RANGE header set"
  f = open(fname, "rb")

  bytes = None

  # is this a range request?
  # looks like: 'HTTP_RANGE': 'bytes=41017-'
  if 'HTTP_RANGE' in web.ctx.environ:
    # try a start only regex
    regex = re.compile('bytes=(\d+)-$')
    grp = regex.match(web.ctx.environ['HTTP_RANGE'])
    if grp:
      start = int(grp.group(1))
      print "player issued range request starting at %d" % start

      f.seek(start)
      bytes = f.read()
      f.close()
      return bytes

    # try a span regex
    regex = re.compile('bytes=(\d+)-(\d+)$')
    grp = regex.match(web.ctx.environ['HTTP_RANGE'])
    if grp:
      start,end = int(grp.group(1)), int(grp.group(2))
      print "player issued range request starting at %d and ending at %d" % (start, end)

      f.seek(start)
      bytes = f.read(end-start)
      f.close()
      return bytes
    
    # don't bother implementing end-only... who uses it?

  else:
    # write the whole thing
    bytes = f.read()
    f.close()
    return bytes

class MediaHandler:
  "retrieve a song"

  def GET(self):
    song = web.input(name = None)
    if not song.name:
      return

    name = song.name
    size = os.stat(name).st_size

    # make a guess at mime type
    ext = os.path.splitext(os.path.split(name)[1] or "")[1].lower()

    if ext == ".mp3":
      web.header("Content-Type", "audio/mpeg")
    elif ext == ".wma":
      web.header("Content-Type", "audio/x-ms-wma")
    elif ext == ".m4v":
      web.header("Content-Type", "video/mp4")

      print str(web.ctx.environ)

    else:
      web.header("Content-Type", "audio/mpeg")

    web.header("Content-Length", "%d" % size)
    return range_handler(name)

class ImageHandler:
  "retrieve album art"

  def GET(self):
    img = web.input(name = None)
    if not img.name:
      return

    size = os.stat(img.name).st_size
    web.header("Content-Type", "image/jpeg")
    web.header("Content-Length", "%d" % size)
    return range_handler(img.name)

class RssHandler:
  def GET(self):
    "retrieve a specific feed"

    config = common.parse_config(config_file)
    collapse_collections = config.get("config", "collapse_collections").lower() == "true"

    web.header("Content-Type", "application/rss+xml")
    feed = web.input(dir = None)
    if feed.dir:
      return getdoc(feed.dir, config, collapse_collections).to_xml()
    else:
      return getdoc(config.get("config", 'music_dir'), config).to_xml()

class M3UHandler:
  def GET(self):
    "retrieve a feed in m3u format"

    config = common.parse_config(config_file)

    web.header("Content-Type", "text/plain")
    feed = web.input(dir = None)
    if feed.dir:
      return doc2m3u(getdoc(feed.dir, config, True))
    else:
      return doc2m3u(getdoc(config.get("config", 'music_dir'), config, True))

class EntropyHandler:
  def GET(self):
    "get an xml document full of random integers"

    return get_entropy(100).toxml()

urls = (
    '/feed', 'RssHandler',
    '/media', 'MediaHandler',
    '/m3u', 'M3UHandler',
    '/image', 'ImageHandler',
    '/entropy', 'EntropyHandler')

app = web.application(urls, globals())

if __name__ == "__main__":
  import sys

  config = common.parse_config(config_file)

  sys.argv.append(config.get("config","server_port"))
  app.run()
