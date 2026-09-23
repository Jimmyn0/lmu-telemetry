LMU TELEMETRY
=============

A tool to look at what you do behind the wheel in Le Mans Ultimate: compare
two laps, see where you lose time corner by corner, measure your consistency.
It reads the recordings the game already makes on its own.

The tool SHOWS, it does not judge: no setup advice, only measured facts.

(Le mode d'emploi en français est dans LISEZ-MOI.txt.)


INSTALLATION
------------

There is nothing to install. Put Telemetrie-LMU.exe wherever you like (the
Desktop, a Games folder...) and double-click it.

On the first launch, Windows may show "Windows protected your PC". This is
normal for a program that is not sold by a publisher: click "More info", then
"Run anyway". It will not ask again.


USING IT
--------

1. Double-click Telemetrie-LMU.exe.
2. A black window opens, then the tool appears in your browser.
3. Keep the black window open while you use the tool: it is what runs it.
   Close it when you are done.

Nothing to set up in the game: Le Mans Ultimate records your telemetry on its
own, for every session. Drive, leave the session, and it shows up in the list.

The tool finds the game on its own in your Steam libraries. If it cannot, it
asks you for the folder and explains how to find it. You only do this once.

The tool is available in French and English: the FR | EN button, at the top
right, switches the language. Your choice is remembered.

Nothing leaves your computer: the tool does not connect to any server, and
does not change any game file. It only reads.


UPDATING
--------

New versions are published here:

    https://github.com/Jimmyn0/lmu-telemetry/releases

Simply replace the old Telemetrie-LMU.exe with the new one. Your settings and
corner maps are kept separately, in:

    %LOCALAPPDATA%\Telemetrie LMU

(paste this line into the File Explorer address bar to open it).
The version number is shown at the top right of the tool.


MANUFACTURER LOGOS
------------------

Some brands are shown with a coloured badge instead of their logo: their logos
cannot be redistributed. To see them anyway, put your own images in the
"logos" folder of the folder above, named after the brand as the tool shows
it: Porsche.png, Ferrari.png, Aston Martin.png...


TROUBLESHOOTING
---------------

* "The tool is no longer responding": the black window was closed. Start
  Telemetrie-LMU.exe again.
* A session does not show up: leave the session in the game first (the game
  keeps the file open while it is running).
* Your antivirus blocks the .exe: this is a common false alarm with this kind
  of program. Add an exception, or ask for a new version.
* Anything else: send the person who gave you the tool the message shown and
  the version number.

To uninstall: delete Telemetrie-LMU.exe, and if you wish the folder
%LOCALAPPDATA%\Telemetrie LMU.
