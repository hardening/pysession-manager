# pysession-manager

pysession-manager is a pure python implementation of a FreeRds sessionManager. 
This implementation is trivial. It has hardcoded user / password / domain and is able
to run a greeter for authentication (when nothing is given by the RDP client), and a
desktop application once you have authenticated.

This session manager is able to manage this kind of applications:

* Qt5 application: it will be run with the qfreerds platform plugin. Any kind of application can be run this way: a greeter or an fullscreen application acting like the desktop)
* a weston desktop: weston, the reference wayland compositor, will be run using the freerds backend

# Installing
The communication between FreeRds and its sessionManager is done with protocol buffer. So you will need the protobuf compiler to create the stub to parse protobuf packets.

You can either:

* edit the Makefile to point to the directory that contains the FreeRds protocol definitions (usually FREEDSINSTALLPREFIX/share/protocols/protobuf), and run make;
* or copy the prebuild one that are present in the prebuild directory.

# Running it
To run pysession-manager, just give it its configuration as first argument:

	# python pysession-manager.py config.json


# Configuration file

The configuration is stored in a json config file.

## Sample configuration file
Here's a sample of configuration file for pysession-manager, the paths should be modified to suit your needs.

	{
	"global": {
		"listeningPipe": "FreeRDS_SessionManager",
		"pipesDirectory": "/tmp/.pipe/",
		"ld_library_path": [
			"/home/david/dev/install-freerds/lib",
			"/home/david/dev/install-freerds/lib/x86_64-linux-gnu/"
		]
	},
		
	"qt": {
		"pluginsPath": "/home/david/dev/install-freerds/lib/plugins",
		"variableName": "FREERDS_PIPE_PATH",
		"initialGeometry": "800x600"	
	},
		
	"weston": {
		"initialGeometry": "1024x768"
	},
	    
	"greeter": {
		"template": "qt",
		"path": "/home/david/dev/git/qfreerds_platform/examples/nice_greeter/nice_greeter"
	},
	    
	"desktop": {
		"template": "weston",
	    "path": "/home/david/dev/git/weston/output/src/weston"
	}
	}


## Configuration file documentation

Here's a short documentation of the keys available in the pysession-manager configuration file.

### global
This part configures values that are global to the session manager. The following subkeys are recognized:

* **listeningPipe**: the name of the ICP listening named pipe;
* **pipesDirectory**: the directory where the named pipe will be created;
* **ld\_library\_path**: a list of directories that will be used and put in the **LD\_LIBRARY\_PATH** variable when launching sub-programs;

The default values are:

	"global": {
		"listeningPipe": "FreeRDS_SessionManager",
		"pipesDirectory": "/tmp/.pipe/",
		"ld_library_path": []
	}


## qt
This part sets configuration parameters for Qt5 applications, the following keys are recognized:


* **pluginsPath** : where to search for Qt plugins, this is the value that will be set in the QT\_PLUGIN\_PATH when launching Qt applications;
* **variableName** : the name of the env variable that will hold the named pipe to connect to the FreeRds server. This is set to FREERDS\_PIPE\_PATH by default, you should change it only if you know what you're doing (it probably means that you are coding on qfreerds);
* **initialGeometry** : when the Qt application will start, the qfreerds screen will have this initial geometry. When FreeRds will connect the screen will be resized to the size of the RDP peer.

The default values are:

	"qt": {
		"pluginsPath": None,
		"variableName": "FREERDS_PIPE_PATH",
		"initialGeometry": "800x600"	
	}


## weston
This part sets configuration parameters for the weston desktop, the following key is recognized:

* **initialGeometry** : when weston will start, the headless screen will have this initial geometry. When FreeRds will connect, the screen will be resized to the size of the RDP peer.

The default values are:

	"weston": {
		"initialGeometry": "1024x768"	
	}

## greeter
This parts configures which application will be launched when the sessionManager needs a greeter application to ask for user / password and domain.

The following keys are recognized:

* **template**: the kind of application, for now it can be qt for a Qt5 application or weston to run a weston desktop;
* **path**: the path to the application to launch

The default values are:

	"greeter": {
		"template": "qt",
		"path": None
	}
	    
## desktop
Once the session manager has authenticated you, it will launch an application that will be your desktop. This section gives the parameters for this application.

The following keys are recognized:

* **template**: the kind of application, for now it can be qt for a Qt5 application (probably a fullscreen one) or weston to run a weston desktop;
* **path**: the path to the application to launch

The default values are:
	    
	"desktop": {
		"template": "weston",
	    	"path": None
	}


