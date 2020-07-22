/*
 * Copyright © 2016-2020 EDDiscovery development team
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

using BaseUtils.JSON;
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Net;

namespace BaseUtils
{
    public class GitHubClass : HttpCom
    {
        public static string UserAgent { get; set; } = System.Reflection.Assembly.GetEntryAssembly().GetName().Name + " v" + System.Reflection.Assembly.GetEntryAssembly().FullName.Split(',')[1].Split('=')[1];

        public delegate void LogLine(string text);
        LogLine logger = null;

        public GitHubClass(string server, LogLine lg = null)
        {
            httpserveraddress = server;
            logger = lg;
        }

        public JArray GetAllReleases(int reqmax)
        {

            try
            {
                HttpWebRequest request = WebRequest.Create(httpserveraddress + "releases?per_page=" + reqmax.ToString()) as HttpWebRequest;
                request.UserAgent = UserAgent;
                using (HttpWebResponse response = request.GetResponse() as HttpWebResponse)
                {
                    StreamReader reader = new StreamReader(response.GetResponseStream());
                    string content1 = reader.ReadToEnd();
                    JArray ja = JArray.Parse(content1);
                    return ja;
                }
            }
            catch (Exception ex)
            {
                Trace.WriteLine($"Exception: {ex.Message}");
                Trace.WriteLine($"ETrace: {ex.StackTrace}");
                return null;
            }

        }

        public GitHubRelease GetLatestRelease()
        {

            try
            {
                HttpWebRequest request = WebRequest.Create(httpserveraddress + "releases/latest") as HttpWebRequest;
                request.UserAgent = UserAgent;
                using (HttpWebResponse response = request.GetResponse() as HttpWebResponse)
                {
                    StreamReader reader = new StreamReader(response.GetResponseStream());
                    string content1 = reader.ReadToEnd();
                    JObject ja = JObject.Parse(content1);

                    if (ja != null)
                    {
                        GitHubRelease rel = new GitHubRelease(ja);
                        return rel;
                    }
                    else
                        return null; ;
                }
            }
            catch (Exception ex)
            {
                Trace.WriteLine($"Exception: {ex.Message}");
                Trace.WriteLine($"ETrace: {ex.StackTrace}");
                return null;
            }
        }
    }
}
