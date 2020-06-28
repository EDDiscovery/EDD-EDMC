using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Text;
using System.Threading.Tasks;
using Microsoft.Win32;

namespace PyHarness
{
    public class EDMCHarnessEDDClass      // EDDClass marks this as type to instance.  Names of members follow EDDInterfaces names
    {
        private string storedout;
        private string currentout;
        private string uiout;

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
            int jv = vopts.ContainsIn("JOURNALVERSION=2");
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

            string scriptrunnerfile = Path.Combine(EDMCAppFolder, "runfromscript.txt");

            string progtoexe = null;
            string cmdline = null;
            string workingdir = null;

            if (File.Exists(scriptrunnerfile))
            {
                var pythonpaths = BaseUtils.PythonLaunch.PythonLauncher();

                if (pythonpaths == null)
                    return "!PY Harness Can't find a python launcher";

                try
                {
                    string[] lines = File.ReadAllLines(scriptrunnerfile);

                    string[] runfrom = lines.Where(x => x.StartsWith("RUNFROM=")).Select(x => x).ToArray();
                    string[] console = lines.Where(x => x.StartsWith("CONSOLE=")).Select(x => x).ToArray();

                    if (runfrom.Length == 1 && console.Length == 1)
                    {
                        string filename = runfrom[0].Substring(8);
                        progtoexe = console[0].Substring(8).Equals("true", StringComparison.InvariantCultureIgnoreCase) ? pythonpaths.Item1 : pythonpaths.Item2;
                        workingdir = Path.GetDirectoryName(filename);
                        cmdline = filename;
                    }
                    else
                        return "!Runfromscript.txt in incorrect format";
                }
                catch
                {
                    return "!Cannot read Runfromscript.txt";
                }
            }
            else
            {
                return "! To be done";
                // try and find eddedmc.exe
            }

            pyharness = new Process();
            pyharness.StartInfo.FileName = progtoexe;
            pyharness.StartInfo.Arguments = cmdline;
            pyharness.StartInfo.WorkingDirectory = workingdir;

            System.Diagnostics.Debug.WriteLine("Run {0} {1} in {2}", progtoexe, cmdline, workingdir);
            bool started = pyharness.Start();

            if (!started)
            {
                pyharness.Dispose();
                pyharness = null;
                return "!PY Harness could not start script";
            }

            System.Diagnostics.Debug.WriteLine("EDMC Harness started");
            return "1.0.0.0;PLAYLASTFILELOAD";
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
                    var s = File.AppendText(currentout);         // use an event this way because CloseMainWindow does not work with a GUI window
                    s.WriteLine(f);
                    s.Close();

                    pyharness.WaitForExit(60000);
                    System.Diagnostics.Debug.WriteLine("Stopped python");
                }

                pyharness.Dispose();
                pyharness = null;

                BaseUtilsHelpers.DeleteFileNoError(storedout);
                BaseUtilsHelpers.DeleteFileNoError(currentout);
                BaseUtilsHelpers.DeleteFileNoError(uiout);
            }
            System.Diagnostics.Debug.WriteLine("Unloaded EDMC Harness");
        }

        public void EDDRefresh(string cmd, EDDDLLInterfaces.EDDDLLIF.JournalEntry lastje)
        {
            System.Diagnostics.Debug.WriteLine("EDMC Refresh");

            string f = string.Format("{{\"timestamp\":\"{0}\", \"event\":\"RefreshOver\"}}", DateTime.UtcNow.Truncate(TimeSpan.TicksPerSecond).ToStringZulu());
            var s = File.AppendText(storedout);
            s.WriteLine(f);
            s.Close();
        }

        public void EDDNewJournalEntry(EDDDLLInterfaces.EDDDLLIF.JournalEntry je)
        {
            System.Diagnostics.Debug.WriteLine("EDMC New Journal Entry " + je.utctime);
            string filetoadd = je.stored ? storedout : currentout;
            var s = File.AppendText(filetoadd);
            s.WriteLine(je.json);
            s.Close();
        }

        public void EDDNewUIEvent(string json)
        {
            System.Diagnostics.Debug.WriteLine("EDMC New UI Event " + json);
            var s = File.AppendText(uiout);
            s.WriteLine(json);
            s.Close();
        }

    }
}
