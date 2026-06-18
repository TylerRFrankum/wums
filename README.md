# Disclaimer
This app was created entirely with Claude. I wanted to make this program to solve a specific problem and then spent a lot of time refining it to make it UX friendly, but all the code WAS created by Claude. I believe you should know this. 

As always, please exercise discretion in your deployments.

# What is WUMS?
Webcomic Update Monitoring System, or WUMS herein, is a python script which monitors websites and RSS feeds for updates to webcomics, manages subscriptions and sends notifications to Discord to alert subscribers that a new update has been published to their favorite webcomics. 

This is meant to serve small servers and allow communities to keep track of favorite webcomics. 

# Installation
WUMS will require you to set up a Discord Bot and a Docker Container. The Discord Bot will be responsible for sending messages into the server and managing Discord command interactions from the user's perspective. The Docker Container will be doing the actual checking of comics, managing subscriptions and generating notifications to send to the Discord Bot. 

## Creating the Discord Bot
Navigate to https://discord.com/developers/applications and create a new application. You don't have to name it WUMS, although I think that's a quite clever name that's fun to say. 

### Bot
In the Bot tab, set the toggle labeled Message Content Intent to true. This is a requirement for the Bot to be interactive. 

Click "Reset Token" and then copy that token into a notepad or other temporary space. You'll need it for the next part. 

This section is also where you can set a profile picture and banner for the Bot's appearance 

### OAuth2
In the OAuth2 tab, we're going to generate the invite URL needed to get the Discord Bot into our server. 

In the URL generator, select the following scopes:

 - bot
 - applications.commands

And then in the window that appears below, select the following bot permissions:

 - Send Messages
 - Embed Links
 - Mention Everyone (used for mentioning specific users)
 - Use Slash Commands. 

Copy the URL that is generated at the bottom and invite the bot to your server. 

From here, we'll work on installing the Docker Container. The Discord Bot won't do anything until that part is running.# Markdown syntax guide

## Installing the Docker Container
I believe in using Docker-Compose. As such, I have provided the dockercompose.yaml in the configuration it is intended to run in below. 

  

    services:
      wums:
        image: tfrankum/wums:latest
        container_name: wums
        environment:
          - DISCORD_BOT_TOKEN=YOUR_BOT_TOKEN_HERE
          - DISCORD_CHANNEL_ID=YOUR_CHANNEL_ID_HERE
          - ADMIN_USER_IDS=YOUR_USER_ID_HERE  # Comma-separated list of admin Discord user IDs
          - CHECK_INTERVAL=7200  # Check every 2 hours (7200 seconds)
          - SEND_TEST_NOTIFICATION=true  # Set to false to skip test notification on startup
          - SEND_STARTUP_RSS_NOTIFICATIONS=false  # Set to true to send notifications for current RSS entries on startup
        volumes:
          - ./data:/app/data  # Persistent data storage (comics.json and subscriptions.json)
        restart: unless-stopped

Create docker-compose.yml in your intended run directory and copy the above YAML into that file

You will need to provide the following environment variables in the indicated sections:

 - DISCORD_BOT_TOKEN: This is the Discord Bot token you get from your application's bot tab from the Discord Developer Portal, as established in the Discord Bot section
 - DISCORD_CHANNEL_ID: This is the ID of the channel you want WUMS to post in. This can be gotten by turning on Discord Developer Mode, right clicking the target channel and copying the Channel ID. 
     - Go to your  User Settings  in your Discord client. On Desktop, you can access  User Settings  by clicking on the cogwheel icon near the bottom-left, next to your username.
    - Click on  Advanced  tab from the left-hand sidebar and toggle on  `Developer Mode`.
- ADMIN_USER_IDS: These are the IDs of people who should have access to Admin commands. At the very least, this should be you, but multiple people can be listed as Admins. Like the channel ID from above, you can get this by right clicking on yourself or another profile and copying the User ID

These environment variables are preset, but may be changed. 

- CHECK_INTERVAL: This is the time, in seconds, between checks. 7200 is 2 hours which should be fine. Be wary of pinging a site too often, they may block your IP address. 
- SEND_TEST_NOTIFICATION: This causes WUMS to send a test notification on startup. By default, this is set to true so that on first installation, you can make sure WUMS is able to message your Discord server. After you're sure it's working, you can safely set this to false so it doesn't send a message every time the container restarts which can happen after power outages, etc. 
- SEND_STARTUP_RSS_NOTIFICATIONS: This will send notifications for the RSS feed entries which are read on startup. This will effectively publish the current updates when WUMS starts. This is disabled by default because it also pings users who are subscribed to those comics. Useful for testing with actual data and making sure the ping system works. 

Once you have filled this out, run docker compose up -d (-d for detached) in the directory where docker-compose.yml is to start WUMS. If you left SEND_TEST_NOTIFICATION set to true, you should get a notification in your Discord server from your Discord Bot. 

Congrats! WUMS is installed!
# Usage
## Supported Comic Monitoring Methods
### RSS
Ideally, the webcomic you want to track will publish an RSS feed. Some webcomics automatically publish one without the webmaster's intention as a part of their web presence suite. Often times, you can find the RSS feed by appending /feed to the end of the URL that the comic is hosted on. You may also attempt to CTRL+F search the page for "RSS" to find a link.  

WUMS will expect the URL which hosts the RSS feed which is formatted in XML. WUMS isn't particular about the version of XML since, thankfully, the required tags are mostly the same. 

What can be problematic is that in FANCIER deployments of RSS, the \<description> tag will sometimes contain HTML code. WUMS will make an attempt to extract a caption from the \<description> tag by stripping away nonsense HTML tags and rendering what is left. However, sometimes the formatting is too mangled for WUMS to make sense of. In this case, WUMS will opt not to display a caption. 

### HTML
In cases where a site does not publish an RSS feed, the other method is to point WUMS at a webpage and have it calculate a hash from the HTML that loads. It will then periodically reload the page and check to see if the HTML hash has changed, thus indicating a difference. 

Best practices for this type of monitoring would be to try and see if the webcomic has a "latest" page. Often, a webcomic will display the latest update on a specific page and then that individual update will ALSO have a permanent link. By targeting the latest page, we'll hopefully capture when a new update is published. Do note however that this can lead to spurious alerts if there is a simple text change.

HTML status codes will be recorded so that you can diagnose issues with these comics if they are failing to poll correctly. 

The user agent has been modified to avoid automatically being denied access to the HTML. 
## Commands
These commands are available as native slash commands. Some of these commands are considered "admin" commands and are denoted as such in this document as well as the Discord UI. Only admins whom are registered in the ADMIN_USER_IDS environment variable as configured above will be able to execute these commands. 

All commands will generate ephemeral responses, meaning that the interaction between the user and the bot will not clutter up your channel. 

### /addcomic [admin] \<comic_id> \<name> \<url> \<comic_type> \<color>
This is the first command which you'll likely run once WUMS is connected to your Discord channel. This command will add a comic to the comics.json file with the information you provide the command.  This command expects five arguments. 
#### comic_id
This is the internal ID of the comic, the one YOU the Admin will be using in other commands. My personal advice would be to keep it simple, no spaces, all lowercase. *E.g. vgcats* 
#### name
This is the friendly name which will appear in update alerts and comic selection dialogues. This can contain spaces, hyphens or whatever you need to make it look nice. *E.g. VG Cats*
#### url
This is the URL of either your RSS feed or the page which you want to check for HTML differences
#### comic_type
This argument expects either 'html' or 'rss'. Any other values are invalid. 
#### color
This is the color of the side bar which will appear during notifications. You may enter any hex value as 0xRRGGBB. Common colors such as red, blue, green, light red, light blue, light green, etc. are preset for convenience. 

### /listcomics [admin]
This command allows you to list the comics which are in comics.json. This command is especially useful for listing the comic_id values which are used in all of the admin commands. 

### /inspectcomic [admin] \<comic_id>
This command will generate a test notification along with some extra information in an ephemeral reply. This means that you're able to see what a comic SHOULD output based on the data gathered by the RSS feed without bothering your users with repeated tests. 

For HTML comics, this will display the last three HTTP status codes along with the code returned when this command was run.  

### /togglecomic [admin] \<comic_id>
This command will toggle whether or not a comic is checked for updates. Toggling a comic off effectively disables it as no updates will be registered and therefore no notifications will be generated. This is a soft disable, as compared to /removecomic. 

### /togglecaption [admin] \<comic_id>
This command toggles the caption field on notifications. This is mostly useful for manually disabling garbage captions that the caption parser isn't detecting as garbage itself. Note that if the caption parser detects that there's no valid caption, a caption will not be displayed even if captions are disabled. You can check this using /inspectcomic
### /removecomic [admin] \<comic_id>
This removes a comic from the comics.json file and also removes any instances of this comic from subscriptions.json. This is a permanent deletion and will require you to readd the comic and users to resubscribe to the comic if they would like it tracked again. 

### /subscribe
This command will allow users to subscribe to the comics registered in comics.json

Subscribing to a comic will cause WUMS to mention the user when that comic has a notification generated. Their user ID will be noted in subscriptions.json along with their subscription preferences. 

When users invoke this command, they will be presented with a menu which allows them to selects from comics which they are not subscribed to. If a user is subscribed to all comics, a message will be generated as such. 

### /unsubscribe
This command will allow users to unsubscribe to the comics registered in comics.json

Unsubscribing from a comic will remove that comic from the user's entry in subscriptions.json and WUMS will no longer mention that user when the comic notification is generated. 

When users invoke this command, they will be presented with a menu which allows them to selects from comics which they are subscribed to. If a user is subscribed to no comics, a message will be generated as such. 

### /subscriptions

This command allows users to view their current subscriptions. 

# Conclusion
WUMS is a dinky little project that does things that other Discord bots probably handle better, but I happen to like it a lot. It was created out of a desire to keep up with webcomics I might otherwise forget about since they don't themselves have an update system. 

WUMS is available for you to fork, mutate, do whatever. Make this thing work better for you. My main goals were for this to do what I wanted it to do, update me about webcomics via Discord, and to have certain UX flows that hopefully make sense so that it's not a completely esoteric system to work with. 

I hope, if you deploy this, you get to enjoy being updated about your webcomics.
