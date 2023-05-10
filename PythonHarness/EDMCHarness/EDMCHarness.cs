/*
 * Copyright (C) 2020 EDDiscovery development team
 *
 * Licensed under the Apache License, Version 2.0 (the "License"); you may not use this
 * file except in compliance with the License. You may obtain a copy of the License at
 *
 * http://www.apache.org/licenses/LICENSE-2.0
 * 
 * Unless required by applicable law or agreed to in writing, software distributed under
 * the License is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF
 * ANY KIND, either express or implied. See the License for the specific language
 * governing permissions and limitations under the License.
 * 
 * EDDiscovery is not affiliated with Frontier Developments plc.
 */

using BaseUtils;
using Microsoft.Win32;
using System;
using System.Diagnostics;
using System.IO;
using System.Linq;

namespace EDMCHarness
{
    public class EDMCHarnessEDDClass      // EDDClass marks this as type to instance.  Names of members follow EDDInterfaces names
    {
        private string storedout;
        private string currentout;
        private string uiout;
        private Object lockwrite = new object();

        public EDMCHarnessEDDClass()
        {
            System.Diagnostics.Debug.WriteLine("Made DLL instance of PyHarness");
        }

        EDDDLLInterfaces.EDDDLLIF.EDDCallBacks callbacks;
        Process pyharness;

        public string EDDInitialise(string vstr, string dllfolderp, EDDDLLInterfaces.EDDDLLIF.EDDCallBacks cb)
        {
            System.Diagnostics.Debug.WriteLine("Init func " + vstr + " " + dllfolderp);

            string[] vopts = vstr.Split(';');
            int jv = vopts.ContainsIn("JOURNALVERSION=");
            if (jv == -1 || vopts[jv].Substring(15).InvariantParseInt(0) < 2)       // check journal version exists and is at 2 mininum
                return "!PY Harness requires a more recent host program";

            string EDMCAppFolder = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "EDD-EDMC");

            if (!Directory.Exists(EDMCAppFolder))
                return "!PY Harness EDD-EDMC folder not found";

            callbacks = cb;

            storedout = Path.Combine(EDMCAppFolder, "stored.edd");
            currentout = Path.Combine(EDMCAppFolder, "current.edd");
            uiout = Path.Combine(EDMCAppFolder, "ui.edd");

            BaseUtilsHelpers.DeleteFileNoError(storedout);
            BaseUtilsHelpers.DeleteFileNoError(currentout);
            BaseUtilsHelpers.DeleteFileNoError(uiout);

            string progtoexe = null;
            string cmdline = null;
            string workingdir = null;
            bool consolemode = false;
            bool runit = true;

            string scriptrunnerfile = Path.Combine(EDMCAppFolder, "runfrom.txt");

            if (File.Exists(scriptrunnerfile))
            {
                try
                {
                    string[] lines = File.ReadAllLines(scriptrunnerfile);

                    string[] console = lines.Where(x => x.StartsWith("CONSOLE=")).Select(x => x).ToArray();
                    if (console.Length == 1 && console[0].Substring(8).Equals("true", StringComparison.InvariantCultureIgnoreCase))
                        consolemode = true;

                    string[] script = lines.Where(x => x.StartsWith("SCRIPT=")).Select(x => x).ToArray();

                    if (script.Length == 1)
                    {
                        string filename = script[0].Substring(7);

                        if (filename.Equals("None", StringComparison.InvariantCultureIgnoreCase))
                        {
                            runit = false;
                        }
                        else
                        {
                            var pythonpaths = BaseUtils.PythonLaunch.PythonLauncher();

                            if (pythonpaths != null)
                            {
                                progtoexe = consolemode ? pythonpaths.Item1 : pythonpaths.Item2;
                                workingdir = Path.GetDirectoryName(filename);
                                cmdline = filename;
                            }
                            else
                                return "!PY Harness Can't find a python launcher";
                        }
                    }
                }
                catch
                {
                    return "!Cannot read Runfrom.txt";
                }
            }

            if ( runit && progtoexe == null )        // if to run, and still no program
            {
                // default app folder is programfiles\edd-edmc
                string AppFolder = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.ProgramFiles), "EDD-EDMC");

                RegistryKey k = Registry.LocalMachine.OpenSubKey(@"Software\EDD-EDMC");
                if ( k != null )    // see if installer put a install path key in there
                {
                    Object o1 = k.GetValue("InstallPath");
                    if (o1 != null)
                        AppFolder = o1 as string;
                }

                string App = Path.Combine(AppFolder, consolemode ? "eddedmc.exe" : "eddedmcwin.exe");

                if (!File.Exists(App))
                    return ("!Cannot find application to run");

                progtoexe = App;
                workingdir = Path.GetDirectoryName(App);
                cmdline = "";
            }

            if (progtoexe != null)                  // did we get one..
            {
                pyharness = new Process();
                pyharness.StartInfo.FileName = progtoexe;
                pyharness.StartInfo.Arguments = cmdline;
                pyharness.StartInfo.WorkingDirectory = workingdir;

                System.Diagnostics.Trace.WriteLine(string.Format("Run {0} {1} in {2}", progtoexe, cmdline, workingdir));
                bool started = pyharness.Start();

                if (!started)
                {
                    pyharness.Dispose();
                    pyharness = null;
                    return "!PY Harness could not start script";
                }
            }

            EDMCHarness.Installer.CheckForNewInstallerAsync(installercallback);

            var currentVersion = System.Reflection.Assembly.GetExecutingAssembly().GetVersionString();
            string f = string.Format("{{\"timestamp\":\"{0}\",\"event\":\"Harness-Version\",\"Version\":\"" + currentVersion + "\"}}", DateTime.UtcNow.Truncate(TimeSpan.TicksPerSecond).ToStringZulu());
            Write(storedout, f);

            System.Diagnostics.Trace.WriteLine("EDMC Harness started");
            return "1.0.0.0;PLAYLASTFILELOAD";
        }

        public void installercallback(BaseUtils.GitHubRelease rel)
        {
            string f = string.Format("{{\"timestamp\":\"{0}\",\"event\":\"Harness-NewVersion\",\"Version\":\"" + rel.ReleaseVersion + "\"}}", DateTime.UtcNow.Truncate(TimeSpan.TicksPerSecond).ToStringZulu());
            Write(storedout, f);
        }

        public void EDDTerminate()
        {
            System.Diagnostics.Debug.WriteLine("Unload EDMC Harness");

            if ( pyharness != null )
            {
                if (!pyharness.HasExited)
                {
                    System.Diagnostics.Debug.WriteLine("Order stop");

                    string f = string.Format("{{\"timestamp\":\"{0}\", \"event\":\"ExitProgram\"}}", DateTime.UtcNow.Truncate(TimeSpan.TicksPerSecond).ToStringZulu());
                    Write(currentout, f);
                    pyharness.WaitForExit(10000);
                    System.Diagnostics.Debug.WriteLine("Stopped python");
                }

                pyharness.Dispose();
                pyharness = null;

                BaseUtilsHelpers.DeleteFileNoError(storedout);
                BaseUtilsHelpers.DeleteFileNoError(currentout);
                BaseUtilsHelpers.DeleteFileNoError(uiout);
            }

            System.Diagnostics.Trace.WriteLine("Unloaded EDMC Harness");
        }

        private string lastcmdr = "";       // empty until first refresh, commander otherwise

        public void EDDRefresh(string cmd, EDDDLLInterfaces.EDDDLLIF.JournalEntry lastje)
        {
            System.Diagnostics.Debug.WriteLine("EDMC Refresh {0}", lastcmdr);

            string filetoadd = lastcmdr == "" ? storedout : currentout;     // so, first time, with lastcmdr="", we write to stored. After refresh we write to current

            lastcmdr = lastje.cmdrname;     // now we have performed a first refresh, we record this to screen out duplicate refreshes

            string f = string.Format("{{\"timestamp\":\"{0}\", \"event\":\"RefreshOver\"}}", DateTime.UtcNow.Truncate(TimeSpan.TicksPerSecond).ToStringZulu());
            Write(filetoadd, f);
        }

        public void EDDNewUnfilteredJournalEntry(EDDDLLInterfaces.EDDDLLIF.JournalEntry je)
        {
            if (!je.stored || je.cmdrname != lastcmdr)       // if not stored, or not the same commander as the one at last refresh
            {
                string filetoadd = lastcmdr == "" ? storedout : currentout;     // so, first time, with lastcmdr="", we write to stored. After refresh we write to current
                System.Diagnostics.Debug.WriteLine("EDMC New Journal Entry " + je.utctime + " " + je.name + " -> " + filetoadd);
                Write(filetoadd, je.json);
            }
            else
            {
                System.Diagnostics.Debug.WriteLine("Not sending EDMC New Journal Entry " + je.utctime + " "  + je.name);
            }

        }

        public void EDDNewUIEvent(string json)
        {
            //System.Diagnostics.Debug.WriteLine("EDMC New UI Event " + json);
            Write(uiout,json);
        }

        private void Write(string filetoadd, string txt)
        {
            lock (lockwrite)
            {
                var s = File.AppendText(filetoadd);
                s.WriteLine(txt);
                s.Close();
            }
        }

    }
}
