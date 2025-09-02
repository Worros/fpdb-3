#!/usr/bin/env python

"""GuiBulkImport module for FPDB bulk import functionality.

Copyright 2008-2011 Steffen Schaumburg
This program is free software: you can redistribute it and/or modify
it under the terms of the GNU Affero General Public License as published by
the Free Software Foundation, version 3 of the License.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
GNU General Public License for more details.

You should have received a copy of the GNU Affero General Public License
along with this program. If not, see <http://www.gnu.org/licenses/>.
In the "official" distribution you can find the license in agpl-3.0.txt.
"""

import L10n
_ = L10n.get_translation()

#    Standard Library modules
import os
import sys
from pathlib import Path
from time import time
from typing import Any
from optparse import OptionParser

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QIcon
#from PyQt5.QtWidgets import (
#    QFileDialog,
#    QHBoxLayout,
#    QLabel,
#    QLineEdit,
#    QPushButton,
#    QTreeWidget,
#    QTreeWidgetItem,
#    QVBoxLayout,
#    QWidget,
#)

import Configuration
import Importer
from loggingFpdb import get_logger

#    fpdb/FreePokerTools modules

# logging has been set up in fpdb.py or HUD_main.py, use their settings:
log = get_logger("gui_bulk_import")


class GuiBulkImport():
    """Widget for bulk importing hand history files."""

    # Configuration  -  update these as preferred:
    allow_threads = False  # set to True to try out the threads field

    def load_clicked(self) -> None:
        """Handle load button click event."""
        stored = None
        dups = None
        partial = None
        skipped = None
        errs = None
        ttime = None
        # Does the lock acquisition need to be more sophisticated for multiple dirs?
        # (see comment above about what to do if pipe already open)
        if self.settings["global_lock"].acquire(
            wait=False,
            source="GuiBulkImport",
        ):  # returns false immediately if lock not acquired
            import_dirs = []
            root = self.import_tree.invisibleRootItem()
            for i in range(root.childCount()):
                item = root.child(i)
                if item.checkState(0) == Qt.Checked:
                    path = item.text(1)  # Path is in the second column
                    import_dirs.append(path)

            custom_dir = self.importDir.text()
            if custom_dir:
                import_dirs.append(custom_dir)

            if not import_dirs:
                log.warning("No import directories selected.")
                self.settings["global_lock"].release()
                return

            self.importer.setHandsInDB(self.n_hands_in_db)
            self.importer.setMode("bulk")

            for import_dir in import_dirs:
                self.importer.addBulkImportImportFileOrDir(import_dir, site="auto")

            self.importer.setCallHud(False)

            starttime = time()

            (stored, dups, partial, skipped, errs, ttime) = self.importer.runImport()

            ttime = time() - starttime
            if ttime == 0:
                ttime = 1

            completion_message = (
                f"Bulk import done: Stored: {stored}, Duplicates: {dups}, "
                f"Partial: {partial}, Skipped: {skipped}, Errors: {errs}, "
                f"Time: {ttime} seconds, Stored/second: {(stored + 0.0) / ttime:.0f}"
            )
            log.info(completion_message)

            self.importer.clearFileList()

            self.settings["global_lock"].release()
        else:
            log.warning("bulk import aborted - global lock not available")

    def get_vbox(self) -> Any:
        """Return the main widget container."""
        """Returns the vbox of this thread."""
        return self.layout()

    def __init__(self, settings: Any, config: Any, sql: Any = None, parent: Any = None) -> None:
        """Initialize the bulk import widget."""
        self.settings = settings
        self.config = config

        self.importer = Importer.Importer(self, self.settings, config, sql, self)

        QWidget.__init__(self, parent)
        self.setLayout(QVBoxLayout())

        # Configured import directories
        self.import_tree = QTreeWidget()
        self.import_tree.setColumnCount(2)
        self.import_tree.setHeaderLabels(["Site", "Path"])
        self.import_tree.setColumnWidth(0, 200)

        for site_name, site in self.config.supported_sites.items():
            if site.enabled:
                icon_path = f"icons/{site_name.lower()}.png"
                icon = QIcon(icon_path) if Path(icon_path).exists() else QIcon()

                if site.HH_path and site.HH_path not in ["", "0"]:
                    item = QTreeWidgetItem(self.import_tree, [site_name, site.HH_path])
                    item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
                    item.setCheckState(0, Qt.Unchecked)
                    item.setIcon(0, icon)

                if site.TS_path and site.TS_path not in ["", "0"]:
                    item = QTreeWidgetItem(self.import_tree, [f"{site_name} (Tourney)", site.TS_path])
                    item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
                    item.setCheckState(0, Qt.Unchecked)
                    item.setIcon(0, icon)

        self.layout().addWidget(QLabel("Configured Import Directories:"))
        self.layout().addWidget(self.import_tree)

        # Custom import directory
        custom_dir_layout = QHBoxLayout()
        self.importDir = QLineEdit(self.settings.get("bulkImport-defaultPath", ""))
        custom_dir_layout.addWidget(self.importDir)
        self.chooseButton = QPushButton("Browse...")
        self.chooseButton.setIcon(QIcon("icons/16x16/cil-folder-open.png"))
        self.chooseButton.clicked.connect(self.browseClicked)
        custom_dir_layout.addWidget(self.chooseButton)
        self.layout().addLayout(custom_dir_layout)

        self.load_button = QPushButton("Bulk Import")
        self.load_button.setIcon(QIcon("icons/16x16/cil-cloud-download.png"))
        self.load_button.clicked.connect(self.load_clicked)
        self.layout().addWidget(self.load_button)

        #    see how many hands are in the db and adjust accordingly
        tcursor = self.importer.database.cursor
        tcursor.execute("Select count(1) from Hands")
        row = tcursor.fetchone()
        tcursor.close()
        self.importer.database.rollback()
        self.n_hands_in_db = row[0]

    def browseClicked(self) -> None:
        """Handle browse button click to select import directory."""
        newdir = QFileDialog.getExistingDirectory(
            self,
            caption=("Please choose the path that you want to Auto Import"),
            directory=self.importDir.text(),
        )
        if newdir:
            self.importDir.setText(newdir)


def main(argv=None):
    """main can also be called in the python interpreter, by supplying the command line as the argument."""
    if argv is None:
        argv = sys.argv[1:]

    def destroy(*args):  # call back for terminating the main eventloop
        gtk.main_quit()

    parser = OptionParser()
    parser.add_option("-f", "--file", dest="filename", metavar="FILE", default=None,
                    help=_("Input file"))
    parser.add_option("-c", "--convert", dest="filtername", default=None, metavar="FILTER",
                    help=_("Site")+ " (Absolute, Merge, Everleaf, Full Tilt Poker, PokerStars, ...)") #TODO: dynamically generate list
    parser.add_option("-x", "--failOnError", action="store_true", default=False,
                    help=_("If this option is used it quits with an extended error message if it encounters any error"))
    parser.add_option("-u", "--usage", action="store_true", dest="usage", default=False,
                    help=_("Print some useful one liners"))
    parser.add_option("-s", "--starsarchive", action="store_true", dest="starsArchive", default=False,
                    help=_("Do the required conversion for %s archive format (ie. as provided by support)") % "PokerStars")
    parser.add_option("-F", "--ftparchive", action="store_true", dest="ftpArchive", default=False,
                    help=_("Do the required conversion for %s archive format (ie. as provided by support)") % "Full Tilt Poker")
    parser.add_option("-t", "--testdata", action="store_true", dest="testData", default=False,
                    help=_("Generate and print test data for regression testing"))
    parser.add_option("-C", "--configFile", dest="config", default=None, help=_("Specifies a configuration file."))
    (options, argv) = parser.parse_args(args = argv)

    if options.usage == True:
        #Print usage examples and exit
        print(_("USAGE:"))
        print(('PokerStars ' + _('converter') + ': ./GuiBulkImport.py -c PokerStars -f filename'))
        print(('Full Tilt  ' + _('converter') + ': ./GuiBulkImport.py -c "Full Tilt Poker" -f filename'))
        print(('Everleaf   ' + _('converter') + ': ./GuiBulkImport.py -c Everleaf -f filename'))
        print(('Absolute   ' + _('converter') + ': ./GuiBulkImport.py -c Absolute -f filename'))
        print(('PartyPoker ' + _('converter') + ': ./GuiBulkImport.py -c PartyPoker -f filename'))
        sys.exit(0)

    Configuration.set_logfile("GuiBulkImport-log.txt")
    if options.config:
        config = Configuration.Config(options.config)
    else:
        config = Configuration.Config()

    settings = {}
    if os.name == 'nt': settings['os'] = 'windows'
    else:               settings['os'] = 'linuxmac'

    settings.update(config.get_db_parameters())
    settings.update(config.get_import_parameters())
    settings.update(config.get_default_paths())

    if not options.filename:
        i = GuiBulkImport(settings, config, None)
        main_window = gtk.Window()
        main_window.connect('destroy', destroy)
        main_window.add(i.vbox)
        main_window.show()
        gtk.main()
    else:
        if not options.filtername:
            print(_("You have to select a site with the -c parameter. E.g.:"), "Everleaf   converter: ./GuiBulkImport.py -c Everleaf -f filename")
        #Do something useful
        importer = Importer.Importer(False,settings, config, None)
        # importer.setDropIndexes("auto")
        importer.setDropIndexes(_("don't drop"))
        importer.setFailOnError(options.failOnError)
        importer.setThreads(-1)
        importer.addBulkImportImportFileOrDir(os.path.expanduser(options.filename), site=options.filtername)
        importer.setCallHud(False)
        if options.starsArchive:
            importer.setStarsArchive(True)
        if options.ftpArchive:
            importer.setFTPArchive(True)
        if options.testData:
            importer.setPrintTestData(True)
        (stored, dups, partial, skipped, errs, ttime) = importer.runImport()
        importer.clearFileList(
        print(_('Bulk import done: Stored: %d, Duplicates: %d, Partial: %d, Skipped: %d Errors: %d, Time: %s seconds, Stored/second: %.0f')\
                     % (stored, dups, partial, skipped, errs, ttime, (stored+0.0) / ttime))

if __name__ == '__main__':
    sys.exit(main())
