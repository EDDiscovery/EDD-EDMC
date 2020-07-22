
/*
 * Copyright © 2016 - 2019 EDDiscovery development team
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

using System;
using System.Collections.Generic;
using System.Linq;

public static class ObjectExtensionsStringsNumbers
{
    public static string ToStringInvariant(this int v)
    {
        return v.ToString(System.Globalization.CultureInfo.InvariantCulture);
    }
    public static string ToStringInvariant(this int v, string format)
    {
        return v.ToString(format, System.Globalization.CultureInfo.InvariantCulture);
    }
    public static string ToStringInvariant(this uint v)
    {
        return v.ToString(System.Globalization.CultureInfo.InvariantCulture);
    }
    public static string ToStringInvariant(this uint v, string format)
    {
        return v.ToString(format, System.Globalization.CultureInfo.InvariantCulture);
    }
    public static string ToStringInvariant(this long v)
    {
        return v.ToString(System.Globalization.CultureInfo.InvariantCulture);
    }
    public static string ToStringInvariant(this long v, string format)
    {
        return v.ToString(format, System.Globalization.CultureInfo.InvariantCulture);
    }
    public static string ToStringIntValue(this bool v)
    {
        return v ? "1" : "0";
    }
    public static string ToStringInvariant(this bool? v)
    {
        return (v.HasValue) ? (v.Value ? "1" : "0") : "";
    }
    public static string ToStringInvariant(this double v, string format)
    {
        return v.ToString(format, System.Globalization.CultureInfo.InvariantCulture);
    }
    public static string ToStringInvariant(this double v)
    {
        return v.ToString(System.Globalization.CultureInfo.InvariantCulture);
    }
    public static string ToStringInvariant(this float v, string format)
    {
        return v.ToString(format, System.Globalization.CultureInfo.InvariantCulture);
    }
    public static string ToStringInvariant(this float v)
    {
        return v.ToString(System.Globalization.CultureInfo.InvariantCulture);
    }
    public static string ToStringInvariant(this double? v, string format)
    {
        return (v.HasValue) ? v.Value.ToString(format, System.Globalization.CultureInfo.InvariantCulture) : "";
    }
    public static string ToStringInvariant(this float? v, string format)
    {
        return (v.HasValue) ? v.Value.ToString(format, System.Globalization.CultureInfo.InvariantCulture) : "";
    }
    public static string ToStringInvariant(this int? v)
    {
        return (v.HasValue) ? v.Value.ToString(System.Globalization.CultureInfo.InvariantCulture) : "";
    }
    public static string ToStringInvariant(this int? v, string format)
    {
        return (v.HasValue) ? v.Value.ToString(format, System.Globalization.CultureInfo.InvariantCulture) : "";
    }
    public static string ToStringInvariant(this long? v)
    {
        return (v.HasValue) ? v.Value.ToString(System.Globalization.CultureInfo.InvariantCulture) : "";
    }
    public static string ToStringInvariant(this long? v, string format)
    {
        return (v.HasValue) ? v.Value.ToString(format, System.Globalization.CultureInfo.InvariantCulture) : "";
    }
}


