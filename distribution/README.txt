GHOSTLINE FOR LMU
=================

A tool to look at what you do behind the wheel in Le Mans Ultimate: the
results of your sessions, compare two laps (yours or your friends'), see where
you lose time corner by corner, measure your consistency, and a leaderboard
with friends. It reads the recordings the game already makes on its own.

The tool SHOWS, it does not judge: no setup advice, only measured facts.

(Le mode d'emploi en français est dans LISEZ-MOI.txt.)


INSTALLATION
------------

There is nothing to install. Unzip the file wherever you like (the Desktop,
a Games folder...): you get a GhostLine folder. Double-click GhostLine.exe,
inside it. Keep the whole folder: GhostLine.exe needs the _internal folder
next to it.

For quick access, make a shortcut: right-click GhostLine.exe, then "Send to",
"Desktop (create shortcut)" (on Windows 11, first "Show more options").

On the first launch, Windows may show "Windows protected your PC". This is
normal for a program that is not sold by a publisher: click "More info", then
"Run anyway". It will not ask again.

The very first launch can take about twenty seconds, while Windows checks the
files: do not double-click again. After that, the tool opens in a few seconds.


USING IT
--------

1. Double-click GhostLine.exe.
2. The tool opens in its own window. Close it when you are done.
3. On the very first start, the tool reads all your sessions in the background:
   the list fills up over a minute or two. After that, it is instant.

Nothing to set up in the game: Le Mans Ultimate records your telemetry on its
own, for every session. Drive, leave the session, and it shows up in the list.

The tool finds the game on its own in your Steam libraries. If it cannot, it
asks you for the folder and explains how to find it. You only do this once.

The tool is available in French and English: the FR | EN button, at the top
right, switches the language. Your choice is remembered.

Nothing leaves your computer unless you join a group (see below), and the
tool does not change any game file: it only reads.


LEADERBOARD WITH FRIENDS
------------------------

The Leaderboard tab ranks the online qualifying sessions and races of a whole
group of friends: best laps per track and class, latest races, a page per
driver. A race opens in the Results tab, even a friend's. You can also pick
two laps there, yours or a friend's, best laps or race laps, and compare them
in the Telemetry tab.

To join the group: Leaderboard tab, "Group" card at the top left, "Join a
group", then the code your friend gave you (for example K7M2-QX9P). After
that, everything happens on its own, at every launch and after every session.

What is shared with the group: your in-game driver name, your lap times,
positions and cars in online qualifying and races, the telemetry of your best
laps and of the best lap of each race, so your friends can compare against
them, and the full results of your online races (the other drivers of the
race and its chat included), so they can open them in Results. Nothing else:
not your practice sessions, not your sessions against the AI. "Leave the
group" deletes all of it.


UPDATING
--------

New versions are published here:

    https://github.com/Jimmyn0/lmu-telemetry/releases

Simply replace the old GhostLine folder with the new one. Your settings and
corner maps are kept separately, in:

    %LOCALAPPDATA%\GhostLine

(paste this line into the File Explorer address bar to open it).
The version number is shown at the top right of the tool.

The tool used to be called LMU Telemetry. If you still have Telemetrie-LMU.exe,
delete it: on its first launch, GhostLine picks up your settings and corner
maps on its own.


MANUFACTURER LOGOS
------------------

The brand logos ship with the tool. They are trademarks of their owners, shown
only to recognise the cars: the tool is not affiliated with any manufacturer.
To replace one, put your own image in the "logos" folder of the folder above,
named after the brand as the tool shows it: Porsche.png, Ferrari.png...


TROUBLESHOOTING
---------------

* The tool opens in your browser instead of its own window: keep the message
  that shows up open, closing it stops the tool. If it happens at every launch,
  send the journal.txt file (in %LOCALAPPDATA%\GhostLine) to the person who
  gave you the tool (Microsoft's WebView2 component may be missing; it normally
  comes with Windows 10 and 11).
* A session does not show up: leave the session in the game first (the game
  keeps the file open while it is running).
* Your antivirus blocks the .exe: this is a common false alarm with this kind
  of program. Add an exception, or ask for a new version.
* Anything else: send the person who gave you the tool the message shown and
  the version number.

To uninstall: delete the GhostLine folder, and if you wish the folder
%LOCALAPPDATA%\GhostLine.
