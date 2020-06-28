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

using Microsoft.Win32;
using System;
using System.IO;

namespace BaseUtils
{
    static public class PythonLaunch
    {
        static private Tuple<string,string> PythonCheckSpecificInstall(string root)     // return console exe, window exe.
        {
            RegistryKey k2 = Registry.LocalMachine.OpenSubKey(root);
            if (k2 != null)
            {
                string[] keys = k2.GetSubKeyNames();

                if (keys.Length > 0)
                {
                    try
                    {
                        Array.Sort(keys, delegate (string l, string r) { return new System.Version(l).CompareTo(new System.Version(r)); });   // assending

                        string last = root + "\\" + keys[keys.Length - 1] + @"\InstallPath";

                        RegistryKey k3 = Registry.LocalMachine.OpenSubKey(last);

                        if (k3 != null)
                        {
                            Object oconsole = k3.GetValue("ExecutablePath");
                            if (oconsole != null)
                            {
                                Object owindow = k3.GetValue("WindowedExecutablePath");
                                if (oconsole is string && owindow is string)
                                    return new Tuple<string, string>(oconsole as string, owindow as string);
                            }
                            else
                            {
                                Object def = k3.GetValue("");
                                if ( def is string )
                                {
                                    string path = def as string;
                                    return new Tuple<string, string>(Path.Combine(path,"python.exe"), Path.Combine(path,"pythonw.exe" ));
                                }
                            }
                        }
                    }
                    catch (Exception ex)
                    {
                        System.Diagnostics.Debug.WriteLine("Py " + ex);
                    }
                }
            }

            return null;
        }

        static private Tuple<string,string> PythonCheckPyLauncher(string root)
        {
            RegistryKey k = Registry.LocalMachine.OpenSubKey(root);
            if (k != null)
            {
                Object o1 = k.GetValue("");      // default has  py.exe
                if (o1 is string)
                {
                    string pyexe = o1 as string;
                    return new Tuple<string, string>(pyexe, Path.Combine(Path.GetDirectoryName(pyexe), Path.GetFileNameWithoutExtension(pyexe) + "w" + Path.GetExtension(pyexe)));
                }
            }

            return null;
        }

        static public Tuple<string,string> PythonLauncher()
        {
            var py32bit = PythonCheckPyLauncher(@"SOFTWARE\WOW6432Node\Python\PyLauncher");
            if (py32bit != null)
                return py32bit;

            var py64bit = PythonCheckPyLauncher(@"SOFTWARE\Python\PyLauncher");
            if (py64bit != null)
                return py64bit;

            var chk1 = PythonCheckSpecificInstall(@"SOFTWARE\Python\PythonCore");      
            if (chk1 != null)
                return chk1;

            var chk2 = PythonCheckSpecificInstall(@"SOFTWARE\WOW6432Node\Python\PythonCore");
            if (chk2 != null)
                return chk2;

            return null;
        }
    }
}

