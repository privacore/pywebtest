#!/usr/bin/env python
from __future__ import with_statement
import BaseHTTPServer
from BaseHTTPServer import  HTTPServer
from SocketServer import ThreadingMixIn
import cgi, sys
import os
import time
import socket
import urllib
import urlparse
import cgi
from time import mktime, strptime
import argparse


root_dir = "tests"


def file_content(path):
	"""Return content of file. Empty string for non-existing files"""
	if not os.path.exists(path):
		return ""
	r=""
	try:
		f=open(path,"rb",1000)
		while True:
			b=f.read(1000)
			if b==None or len(b)==0: break;
			r+= b
		f.close()
	except IOError as ex:
		pass
	if r!="" and r[-1]=='\n' and r.count('\n')==1:
		return r.partition('\n')[0]
	return r



class Handler(BaseHTTPServer.BaseHTTPRequestHandler):
	def do_GET(self):
		parsed_url = urlparse.urlparse(self.path)
		host = self.headers["Host"]
		#strip of port from host (eg. www.example.com:80
		host = host.split(':')[0]
		
		#Host is expected to be in the form of <server>.<testcase>.something.....
		if len(host.split('.'))<2:
			return self.respond_unknown_host(host)

		host_parts = host.split('.')
		server = host_parts[0]
		testset = host_parts[1]
		args.domain = ".".join(host_parts[2:len(host_parts)])

		path = parsed_url.path
		
		print "testset=%s, server=%s, path=%s"%(testset,server,path)
		return self.serve_page(testset,server,path)


	def respond_unknown_host(self,host):
		self.send_response(500)
		self.send_header("Content-type", "text/html")
		self.end_headers()
		print >>self.wfile, '<html><body>Host %s is unknown</body></html>'%host
	def respond_unknown_testset(self,testset):
		self.send_response(500)
		self.send_header("Content-type", "text/html")
		self.end_headers()
		print >>self.wfile, '<html><body>testset %s is unknown</body></html>'%testset
	def respond_unknown_server(self,server):
		self.send_response(500)
		self.send_header("Content-type", "text/html")
		self.end_headers()
		print >>self.wfile, '<html><body>server %s is unknown</body></html>'%server


	def serve_page(self, testset, server, path):
		fp = root_dir+"/"+testset

		if not os.path.exists(root_dir+"/"+testset):
			return self.respond_unknown_testset(testset)

		if not os.path.exists(root_dir+"/"+testset+"/"+server):
			return self.respond_unknown_server(server)

		#ok, directory exist so testet and server is known
		base_path = root_dir+"/"+testset+"/"+server+path
		if os.path.isdir(base_path):
			return self.maybe_serve_index_page(base_path, path)
		if not os.path.exists(base_path):
			return self.respond_not_found(base_path)
		
		#Setup defaults
		status_code = 200
		content_type = "application/octet-stream"
		content_transfer_encoding = None
		charset = None
		extra_headers = []
		
		extension = path.split('.')[-1]
		if extension=="html":
			content_type = "text/html"
			charset = "UTF-8"
		elif extension=="txt":
			content_type = "text/plain"
			charset = "UTF-8"
		elif extension=="txt":
			content_type = "text/plain"
			charset = "UTF-8"
		elif extension=="png":
			content_type = "image/png"
		elif extension=="gif":
			content_type = "image/gif"
		elif extension=="jpg" or extension=="jpeg":
			content_type = "image/jpeg"
		elif extension=="c" or extension=="h":
			content_type = "text/x-csrc"
			charset = "UTF-8"
		elif extension=="cc" or extension=="cpp" or extension=="hpp":
			content_type = "text/x-c++src"
			charset = "UTF-8"
		elif extension=="pdf":
			content_type = "application/pdf"
		elif extension=="docx":
			content_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
		elif extension=="pptx":
			content_type = "application/vnd.openxmlformats-officedocument.presentationml.presentation"
		elif extension==".xlsx":
			content_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
		elif extension==".odt":
			content_type = "application/vnd.oasis.opendocument.text"
		elif extension==".odp":
			content_type = "application/vnd.oasis.opendocument.presentation"
		elif extension==".ods":
			content_type = "application/vnd.oasis.opendocument.spreadsheet"
		
		#then look for overrides
		if os.path.exists(base_path+".status-code"):
			status_code = int(file_content(base_path+".status-code"))
		if os.path.exists(base_path+".content-type"):
			content_type = file_content(base_path+".content-type").strip()
		if os.path.exists(base_path+".charset"):
			charset = file_content(base_path+".charset").strip()
		if os.path.exists(base_path+".content-transfer-encoding"):
			content_transfer_encoding = file_content(base_path+".content-transfer-encoding").strip()
		if os.path.exists(base_path+".extra-headers"):
			extra_headers = file_content(base_path+".extra-headers").split('\n')
		
		if content_type=="":
			content_type=None
		if charset=="":
			charset=None
		if content_transfer_encoding=="":
			content_transfer_encoding=None
		
		#ok, got it all
		self.send_response(status_code)
		if content_type is not None:
			if charset is None:
				self.send_header("Content-type", content_type)
			else:
				self.send_header("Content-type", content_type + "; charset=" + charset)
		for h in extra_headers:
			self.send_header(h.split(":")[0],h.partition(":")[2])
		self.end_headers()

		with open(base_path,"rb") as f:
			content = f.read()
			content = content.replace("${DOMAIN}", args.domain )
			content = content.replace("${PORT}", str(args.port) )
			self.wfile.write(content)
	
	def maybe_serve_index_page(self, dir, path):
		if os.path.exists(dir+"/_noindex"):
			self.send_response(404)
			self.end_headers()
			return

		self.send_response(200)
		self.send_header("Content-type", "text/html")
		self.end_headers()

		if os.path.exists(dir + "/index.html"):
			with open(dir + "/index.html", "rb") as f:
				self.wfile.write(f.read())
			return

		print >>self.wfile, "<html>"
		print >>self.wfile, "<head>"
		print >>self.wfile, "    <title>Contents of %s</title>"%(dir)
		print >>self.wfile, "</head>"
		print >>self.wfile, "<body>"

		l = os.listdir(dir)
		l.sort()

		special_ending = ('.status-code', '.content-type', '.charset', '.content-transfer-encoding', '.extra-headers')
		special_file = ('README')
		filedir = "" if (path == "/") else path
		for f in l:
			if not f.endswith(special_ending) and f not in special_file:
				print >>self.wfile, '<p><a href="%s/%s">%s</a></p>'%(filedir,f,f)

		print >>self.wfile, "</body>"
		print >>self.wfile, "</html>"
	
	
	def respond_not_found(self,path):
		self.send_response(404)
		self.send_header("Content-type", "text/html")
		self.end_headers()
		print >>self.wfile, '<html><body>404 - %s was not found</body></html>'%path



class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
	"""Handle requests in a separate thread."""
	pass


parser = argparse.ArgumentParser()
parser.add_argument("-p", "--port", type=int, help="HTTP server port number", default=8080)

args = parser.parse_args()

httpd = ThreadedHTTPServer(("", args.port), Handler)
httpd.serve_forever()
