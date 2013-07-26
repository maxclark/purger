#!/usr/bin/env python
import cgi
import cgitb
import ConfigParser
import httplib
import os
import re
import socket
import urlparse


def table_head(caption):
	"""
	prints the table head with the caption given as param
	"""

	return('''
	<p><table style="border:1px solid gray">
	<caption>%s</caption>
	<tr><th>Server</th><th>Status</th><th>HTTP Status</h1></tr>
	''' % caption )

def table_footer():
	"""
	prints the table footer
	"""

	return('''
	<p></table>
	''')

def theform():
	"""
	simply returns the form
	"""

	return('''
	<form action="" method="POST">
	<fieldset>
	<legend>URL to purge from caches</legend>
	<table>
	<tr><td><label for="url">URL</label></td><td><input type="text" id="url" name="URL"/></tr>
	<tr><td colspan="2"><input type="submit" /></td></tr>
	</table>
	</fieldset>
	</form>
	''')

def error_message(message='Something went wrong',severity='info'):
	"""
	Prints out an error message colorized according to it's severity
	"""
	if severity == 'fatal':
		color = 'red'
	elif severity == 'warning':
		color = 'darkorange'
	elif severity=='info':
		color = 'navy'
	return('''
	<p><span style="color:%(color)s;font-weight:bold;">%(message)s</span></p>
	''' % locals())

def validate_url(url):
	"""
	validates the url to be a valid http(s) address,
	either per IP or domain
	"""
	url_re = re.compile(
		r'^https?://' # http:// or https://
		r'(?:(?:[A-Z0-9-]+\.)+[A-Z]{2,6}|' #domain...
		r'localhost|' #localhost...
		r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})' # ...or ip
#		r'(?::\d+)?' # optional port
		r'(?:/?|/\S+)$', re.IGNORECASE)
	if url_re.match(url):
		return True
	else:
		return False

def create_varnish_parts(url):
	"""
	splits the given url in parts usable for vanrnishes special demands
	"""
	splitted = urlparse.urlsplit(url)

	# if splitted.path == '':

	# Hack to make this work with python2.3
	if splitted[2] == '':
		# make sure we have a valid request
		path = '/'
	else:
		path = splitted.path
	return {'host': '%s://%s' %(splitted.scheme,splitted.netloc),
		'path': '%s' %(path)}

def split_host_port(server):
	"""
	splits the host and the port part of a given server
	"""
	splitted = server.split(':',1)
	try:
		assert len(splitted) > 1	
		return {'host':splitted[0],'port':splitted[1]}
	except AssertionError:
		return 	None

def process_purge(target_server,url,type):
	"""
	Does the actual purging.
	Depending on the type (either 'varnish' or 'squid') the request header will be adjusted
	"""

	try:
		server = split_host_port(target_server)
		assert server is not None
	except AssertionError:
		return '<tr><td>%s</td><td>%s</td><td>%s</td></tr>' % (target_server, 'Malformed config entry' , 'None')
	try:
		if type == 'varnish':
			target = create_varnish_parts(url)
			conn = httplib.HTTPConnection(server['host'],server['port'],{'Host':target['host']})
			conn.request("PURGE",target['path'])
		elif type=='squid':
			conn 	= httplib.HTTPConnection(server['host'],server['port'])
			conn.request("PURGE",url)

		resp = conn.getresponse()
		if resp.status == 200:
			message = "Purged"
		elif resp.status == 404:
			message = "Not in Cache"
		else:
			message = resp.reason
		return '<tr><td>%s</td><td>%s</td><td>%s</td></tr>' % (target_server, message, resp.status)
	except httplib.HTTPException, e:
		print error_message(e,'fatal')
		exit(1)
	except socket.error, (errno, strerror):
		return '<tr><td>%s</td><td>%s</td><td>%s</td></tr>' % (target_server, strerror , errno)

def process_servers(cache_name,cache_type,url,config):	

	try:
		# has to be done via an assertion, since ConfigParser does not
		# throw an exception on an empty config item
		caches	= config.get(cache_type,'servers').split()
		assert len(caches) > 0

		print table_head('%s Caches' % cache_name)

		for cache in caches:
			print process_purge(cache,url,cache_type)

		print table_footer

	except AssertionError:
		print error_message('No %(cache_type)s caches defined' % locals())

	except ConfigParser.NoOptionError:
		print error_message('Section [%(cache_type)s] of config file has no option servers' % locals(),'warning')

	except ConfigParser.NoSectionError:
		print error_message('Section [%(cache_type)s] does not exist in the config file'% locals())

def main():
	# enable traceback in case something goes wrong
	cgitb.enable()

	print 'Content-type: text/html\n\n'
	print '''
	<html><head><title>Purge Caches</title>
	<style type="text/css">
		table {
			border-collapse: collapse;
			table-layout: auto;
			width: auto;
		}
		tr{ border:thin solid gray; }
		th,td { padding: 0.5em 1em;}
		body {
			margin:50px 0px; padding:0px;
			text-align:center;
			font-family:Verdana,Tahoma, sans;
			}
	
		#Content {
			width:500px;
			width:50%;
			margin:0px auto;
			text-align:left;
			padding:15px;
			border:1px dashed #333;
			}

	</style>
	<body>
	<div id="content">
	'''

	form = cgi.FieldStorage()

	if form and form.has_key("URL") and form["URL"] != "":
		if validate_url(form["URL"].value):
			
			# We dont need the config file earlier
			if not os.access('/etc/purger.conf',os.R_OK):
				print error_message('Watch out! Configuration file /etc/purger.conf not accessible','fatal')
				exit(1)

			print "<h3>Submitted %s</h3>" % form["URL"].value
			config = ConfigParser.ConfigParser()
			try:
				config.read('/etc/purger.conf')
			except ConfigParser.MissingSectionHeaderError, e:
				print error_message('The file %s has an error in line %s: %s' % (e.filename,e.lineno,e.message),'fatal')
				exit(1)
			except ConfigParser.ParsingError,e:
				print error_message('%s' % e.message, 'fatal')
				exit(1)

			#
			# START PROCESSING THE VARNISH CACHES
			#

			process_servers('Varnish','varnish',form['URL'].value,config)

			#
			# START PROCESSING THE SQUID CACHES
			#

			process_servers('Squid','squid',form['URL'].value,config)

		else:
			print error_message("Not a valid url",'fatal')
	elif not form:
		print theform()
	else:
		print error_message(severity='fatal')
	print "</div></body></html>"
main()

