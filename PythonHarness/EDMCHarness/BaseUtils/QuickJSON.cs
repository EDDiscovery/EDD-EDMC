/*
 * Copyright © 2020 robby & EDDiscovery development team
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
using System.Collections;
using System.Collections.Generic;

namespace BaseUtils.JSON
{
    // small light JSON decoder and encoder.

    // JToken is the base class, can parse, encode

    public abstract class JToken : IEnumerable<JToken>, IEnumerable
    {
        public enum TType { Null, Boolean, String, Double, Long, Ulong, BigInt, EndObject, EndArray, Object, Array }
        public TType ttype;     // using a ttype faster than using X is ..

        public static implicit operator JToken(string v)
        {
            return new JString(v);
        }
        public static implicit operator JToken(long v)
        {
            return new JLong(v);
        }
        public static implicit operator JToken(ulong v)
        {
            return new JULong(v);
        }
        public static implicit operator JToken(double v)
        {
            return new JDouble(v);
        }
        public static implicit operator JToken(bool v)
        {
            return new JBoolean(v);
        }

        public virtual JToken this[object key] { get { return null; } set { throw new NotImplementedException(); } }

        public IEnumerator<JToken> GetEnumerator()
        {
            return GetSubClassTokenEnumerator();
        }

        public virtual IEnumerator<JToken> GetSubClassTokenEnumerator() { throw new NotImplementedException(); }

        IEnumerator IEnumerable.GetEnumerator()
        {
            return GetSubClassEnumerator();
        }

        public virtual IEnumerator GetSubClassEnumerator() { throw new NotImplementedException(); }

        bool IsString { get { return ttype == TType.String; } }
        bool IsInt { get { return ttype == TType.Long || ttype == TType.Ulong || ttype == TType.BigInt; } }
        bool IsBigInt { get { return ttype == TType.BigInt; } }
        bool IsULong { get { return ttype == TType.Ulong; } }
        bool IsDouble { get { return ttype == TType.Double || ttype == TType.Long; } }
        bool IsBool { get { return ttype == TType.Boolean; } }
        bool IsArray { get { return ttype == TType.Array; } }
        bool IsObject { get { return ttype == TType.Object; } }
        bool IsNull { get { return ttype == TType.Null; } }

        public string Str(string def = "")
        {
            return ttype == TType.String ? ((JString)this).Value : def;
        }

        public int Int(int def = 0)
        {
            return ttype == TType.Long ? (int)((JLong)this).Value : def;
        }

        public long Long(long def = 0)
        {
            return ttype == TType.Long ? ((JLong)this).Value : def;
        }

        public ulong ULong(ulong def = 0)
        {
            if (ttype == TType.Ulong)
                return ((JULong)this).Value;
            else if (ttype == TType.Long && ((JLong)this).Value >= 0)
                return (ulong)((JLong)this).Value;
            else
                return def;
        }

        public System.Numerics.BigInteger BigInteger(System.Numerics.BigInteger def)
        {
            if (ttype == TType.Ulong)
                return ((JULong)this).Value;
            else if (ttype == TType.Long)
                return (ulong)((JLong)this).Value;
            else if (ttype == TType.BigInt)
                return ((JBigInteger)this).Value;
            else
                return def;
        }

        public bool Bool(bool def = false)
        {
            return ttype == TType.Boolean ? ((JBoolean)this).Value : def;
        }

        public double Double(double def = 0)
        {
            return ttype == TType.Double ? ((JDouble)this).Value : (ttype == TType.Long ? (double)((JLong)this).Value : def);
        }

        public DateTime? DateTime(System.Globalization.CultureInfo ci, System.Globalization.DateTimeStyles ds = System.Globalization.DateTimeStyles.AssumeUniversal | System.Globalization.DateTimeStyles.AdjustToUniversal)
        {
            if (ttype == TType.String && System.DateTime.TryParse(((JString)this).Value, ci, ds, out DateTime ret))
                return ret;
            else
                return null;
        }

        public DateTime DateTime(DateTime defvalue, System.Globalization.CultureInfo ci, System.Globalization.DateTimeStyles ds = System.Globalization.DateTimeStyles.AssumeUniversal | System.Globalization.DateTimeStyles.AdjustToUniversal)
        {
            if (ttype == TType.String && System.DateTime.TryParse(((JString)this).Value, ci, ds, out DateTime ret))
                return ret;
            else
                return defvalue;
        }

        public JArray Array()       // null if not
        {
            return this as JArray;
        }

        public JObject Object()     // null if not
        {
            return this as JObject;
        }

        public override string ToString()
        {
            return ToString(false);
        }

        public string ToString(bool verbose = false, string pad = "  ")
        {
            return verbose ? ToString(this, "", "\r\n", pad) : ToString(this, "", "", "");
        }

        public static string ToString(JToken o, string prepad, string postpad, string pad)
        {
            if (o.ttype == TType.String)
                return prepad + "\"" + ((JString)o).Value.EscapeControlCharsFull() + "\"" + postpad;
            else if (o.ttype == TType.Double)
                return prepad + ((JDouble)o).Value.ToStringInvariant() + postpad;
            else if (o.ttype == TType.Long)
                return prepad + ((JLong)o).Value.ToStringInvariant() + postpad;
            else if (o.ttype == TType.Ulong)
                return prepad + ((JULong)o).Value.ToStringInvariant() + postpad;
            else if (o.ttype == TType.BigInt)
                return prepad + ((JBigInteger)o).Value.ToString(System.Globalization.CultureInfo.InvariantCulture) + postpad;
            else if (o.ttype == TType.Boolean)
                return prepad + ((JBoolean)o).Value.ToString().ToLower() + postpad;
            else if (o.ttype == TType.Null)
                return prepad + "null" + postpad;
            else if (o.ttype == TType.Array)
            {
                string s = prepad + "[" + postpad;
                string prepad1 = prepad + pad;
                JArray ja = o as JArray;
                for (int i = 0; i < ja.Elements.Count; i++)
                {
                    bool notlast = i < ja.Elements.Count - 1;
                    s += ToString(ja.Elements[i], prepad1, postpad, pad);
                    if (notlast)
                    {
                        s = s.Substring(0, s.Length - postpad.Length) + "," + postpad;
                    }
                }
                s += prepad + "]" + postpad;
                return s;
            }
            else if (o.ttype == TType.Object)
            {
                string s = prepad + "{" + postpad;
                string prepad1 = prepad + pad;
                int i = 0;
                JObject jo = ((JObject)o);
                foreach (var e in jo.Objects)
                {
                    bool notlast = i++ < jo.Objects.Count - 1;
                    if (e.Value is JObject || e.Value is JArray)
                    {
                        s += prepad1 + "\"" + e.Key.EscapeControlCharsFull() + "\":" + postpad;
                        s += ToString(e.Value, prepad1, postpad, pad);
                        if (notlast)
                        {
                            s = s.Substring(0, s.Length - postpad.Length) + "," + postpad;
                        }
                    }
                    else
                    {
                        s += prepad1 + "\"" + e.Key.EscapeControlCharsFull() + "\":" + ToString(e.Value, "", "", pad) + (notlast ? "," : "") + postpad;
                    }
                }
                s += prepad + "}" + postpad;
                return s;
            }
            else
                return null;
        }

        public static JToken Parse(string s)        // null if failed.
        {
            StringParser2 parser = new StringParser2(s);
            return Decode(parser, out string unused);
        }

        public static JToken Parse(string s, bool checkeol)        // null if failed - must not be extra text
        {
            StringParser2 parser = new StringParser2(s);
            JToken res = Decode(parser, out string unused);
            return parser.IsEOL ? res : null;
        }

        public static JToken Parse(string s, out string error, bool checkeol = false)
        {
            StringParser2 parser = new StringParser2(s);
            JToken res = Decode(parser, out error);
            return parser.IsEOL || !checkeol ? res : null;
        }

        // null if its unhappy and error is set
        // decoder does not worry about extra text after the object.

        static private JToken Decode(StringParser2 parser, out string error)
        {
            error = null;

            JToken[] stack = new JToken[256];
            int sptr = 0;
            bool comma = false;
            JArray curarray = null;
            JObject curobject = null;

            // first decode the first value/object/array
            {
                int decodestartpos = parser.Position;

                JToken o = DecodeValue(parser, false);       // grab new value, not array end

                if (o == null)
                {
                    error = GenError(parser, decodestartpos);
                    return null;
                }
                else if (o.ttype == TType.Array)
                {
                    stack[++sptr] = o;          // push this one onto stack
                    curarray = o as JArray;                 // this is now the current object
                }
                else if (o.ttype == TType.Object)
                {
                    stack[++sptr] = o;          // push this one onto stack
                    curobject = o as JObject;                 // this is now the current object
                }
                else
                {
                    return o;       // value only
                }
            }

            while (true)
            {
                if (curobject != null)      // if object..
                {
                    while (true)
                    {
                        int decodestartpos = parser.Position;

                        char next = parser.GetChar();

                        if (next == '}')    // end object
                        {
                            parser.SkipSpace();

                            if (comma == true)
                            {
                                error = GenError(parser, decodestartpos);
                                return null;
                            }
                            else
                            {
                                JToken prevtoken = stack[--sptr];
                                if (prevtoken == null)      // if popped stack is null, we are back to beginning, return this
                                {
                                    return stack[sptr + 1];
                                }
                                else
                                {
                                    comma = parser.IsCharMoveOn(',');
                                    curobject = prevtoken as JObject;
                                    if (curobject == null)
                                    {
                                        curarray = prevtoken as JArray;
                                        break;
                                    }
                                }
                            }
                        }
                        else if (next == '"')   // property name
                        {
                            string name = parser.NextQuotedWordString(next, true);

                            if (name == null || (comma == false && curobject.Objects.Count > 0) || !parser.IsCharMoveOn(':'))
                            {
                                error = GenError(parser, decodestartpos);
                                return null;
                            }
                            else
                            {
                                decodestartpos = parser.Position;

                                JToken o = DecodeValue(parser, false);      // get value

                                if (o == null)
                                {
                                    error = GenError(parser, decodestartpos);
                                    return null;
                                }

                                curobject.Objects[name] = o;  // assign to dictionary

                                if (o.ttype == TType.Array) // if array, we need to change to this as controlling object on top of stack
                                {
                                    if (sptr == stack.Length - 1)
                                    {
                                        error = "Recursion too deep";
                                        return null;
                                    }

                                    stack[++sptr] = o;          // push this one onto stack
                                    curarray = o as JArray;                 // this is now the current object
                                    curobject = null;
                                    comma = false;
                                    break;
                                }
                                else if (o.ttype == TType.Object)   // if object, this is the controlling object
                                {
                                    if (sptr == stack.Length - 1)
                                    {
                                        error = "Recursion too deep";
                                        return null;
                                    }

                                    stack[++sptr] = o;          // push this one onto stack
                                    curobject = o as JObject;                 // this is now the current object
                                    comma = false;
                                }
                                else
                                {
                                    comma = parser.IsCharMoveOn(',');
                                }
                            }
                        }
                        else
                        {
                            error = GenError(parser, decodestartpos);
                            return null;
                        }
                    }
                }
                else
                {
                    while (true)
                    {
                        int decodestartpos = parser.Position;

                        JToken o = DecodeValue(parser, true);       // grab new value

                        if (o == null)
                        {
                            error = GenError(parser, decodestartpos);
                            return null;
                        }
                        else if (o.ttype == TType.EndArray)          // if end marker, jump back
                        {
                            if (comma == true)
                            {
                                error = GenError(parser, decodestartpos);
                                return null;
                            }
                            else
                            {
                                JToken prevtoken = stack[--sptr];
                                if (prevtoken == null)      // if popped stack is null, we are back to beginning, return this
                                {
                                    return stack[sptr + 1];
                                }
                                else
                                {
                                    comma = parser.IsCharMoveOn(',');
                                    curobject = prevtoken as JObject;
                                    if (curobject == null)
                                    {
                                        curarray = prevtoken as JArray;
                                    }
                                    else
                                        break;
                                }
                            }
                        }
                        else if ((comma == false && curarray.Elements.Count > 0))   // missing comma
                        {
                            error = GenError(parser, decodestartpos);
                            return null;
                        }
                        else
                        {
                            curarray.Elements.Add(o);

                            if (o.ttype == TType.Array) // if array, we need to change to this as controlling object on top of stack
                            {
                                if (sptr == stack.Length - 1)
                                {
                                    error = "Recursion too deep";
                                    return null;
                                }

                                stack[++sptr] = o;              // push this one onto stack
                                curarray = o as JArray;         // this is now the current array
                                comma = false;
                            }
                            else if (o.ttype == TType.Object) // if object, this is the controlling object
                            {
                                if (sptr == stack.Length - 1)
                                {
                                    error = "Recursion too deep";
                                    return null;
                                }

                                stack[++sptr] = o;              // push this one onto stack
                                curobject = o as JObject;       // this is now the current object
                                curarray = null;
                                comma = false;
                                break;
                            }
                            else
                            {
                                comma = parser.IsCharMoveOn(',');
                            }
                        }
                    }
                }
            }
        }

        static JEndArray jendarray = new JEndArray();

        // return JObject, JArray, char indicating end array if inarray is set, string, long, ulong, bigint, true, false, JNull
        // null if unhappy

        static private JToken DecodeValue(StringParser2 parser, bool inarray)
        {
            //System.Diagnostics.Debug.WriteLine("Decode at " + p.LineLeft);
            char next = parser.GetChar();
            switch (next)
            {
                case '{':
                    parser.SkipSpace();
                    return new JObject();

                case '[':
                    parser.SkipSpace();
                    return new JArray();

                case '"':
                    string value = parser.NextQuotedWordString(next, true);
                    return value != null ? new JString(value) : null;

                case ']':
                    if (inarray)
                    {
                        parser.SkipSpace();
                        return jendarray;
                    }
                    else
                        return null;

                case '0':       // all positive. JSON does not allow a + at the start (integer fraction exponent)
                case '1':
                case '2':
                case '3':
                case '4':
                case '5':
                case '6':
                case '7':
                case '8':
                case '9':
                    parser.BackUp();
                    return parser.NextJValue(false);
                case '-':
                    return parser.NextJValue(true);
                case 't':
                    return parser.IsStringMoveOn("rue") ? new JBoolean(true) : null;
                case 'f':
                    return parser.IsStringMoveOn("alse") ? new JBoolean(false) : null;
                case 'n':
                    return parser.IsStringMoveOn("ull") ? new JNull() : null;

                default:
                    return null;
            }
        }

        static private string GenError(StringParser2 parser, int start)
        {
            int enderrorpos = parser.Position;
            string s = "JSON Error at " + start + " " + parser.Line.Substring(0, start) + " <ERROR>"
                            + parser.Line.Substring(start, enderrorpos - start) + "</ERROR>" +
                            parser.Line.Substring(enderrorpos);
            System.Diagnostics.Debug.WriteLine(s);
            return s;
        }
    }

    public class JNull : JToken
    {
        public JNull() { ttype = TType.Null; }
    }
    public class JBoolean : JToken
    {
        public JBoolean(bool v) { ttype = TType.Boolean; Value = v; }
        public bool Value { get; set; }
    }
    public class JString : JToken
    {
        public JString(string s) { ttype = TType.String; Value = s; }
        public string Value { get; set; }
    }
    public class JLong : JToken
    {
        public JLong(long v) { ttype = TType.Long; Value = v; }
        public long Value { get; set; }
    }
    public class JULong : JToken
    {
        public JULong(ulong v) { ttype = TType.Ulong; Value = v; }
        public ulong Value { get; set; }
    }
    public class JBigInteger : JToken
    {
        public JBigInteger(System.Numerics.BigInteger v) { ttype = TType.BigInt; Value = v; }
        public System.Numerics.BigInteger Value { get; set; }
    }
    public class JDouble : JToken
    {
        public JDouble(double d) { ttype = TType.Double; Value = d; }
        public double Value { get; set; }
    }
    public class JEndObject : JToken    // internal, only used during decode
    {
        public JEndObject() { ttype = TType.EndObject; }
    }
    public class JEndArray : JToken     // internal, only used during decode
    {
        public JEndArray() { ttype = TType.EndArray; }
    }

    public class JObject : JToken, IEnumerable<KeyValuePair<string, JToken>>
    {
        public JObject()
        {
            ttype = TType.Object;
            Objects = new Dictionary<string, JToken>(16);   // giving a small initial cap seems to help
        }

        public Dictionary<string, JToken> Objects { get; set; }

        public override JToken this[object key] { get { System.Diagnostics.Debug.Assert(key is string); return Objects[(string)key]; } set { System.Diagnostics.Debug.Assert(key is string); Objects[(string)key] = value; } }
        public JToken this[string key] { get { return Objects[key]; } set { Objects[key] = value; } }
        public bool ContainsKey(string n) { return Objects.ContainsKey(n); }
        public int Count() { return Objects.Count; }
        public bool Remove(string key) { return Objects.Remove(key); }
        public void Clear() { Objects.Clear(); }

        public new static JObject Parse(string s)        // null if failed.
        {
            var res = JToken.Parse(s);
            return res as JObject;
        }

        public new static JObject Parse(string s, out string error, bool checkeol = false)
        {
            var res = JToken.Parse(s, out error, checkeol);
            return res as JObject;
        }

        public new IEnumerator<KeyValuePair<string, JToken>> GetEnumerator() { return Objects.GetEnumerator(); }
        public override IEnumerator<JToken> GetSubClassTokenEnumerator() { return Objects.Values.GetEnumerator(); }
        public override IEnumerator GetSubClassEnumerator() { return Objects.GetEnumerator(); }
    }

    public class JArray : JToken
    {
        public JArray()
        {
            ttype = TType.Array;
            Elements = new List<JToken>(16);
        }

        public List<JToken> Elements { get; set; }

        public override JToken this[object key] { get { System.Diagnostics.Debug.Assert(key is int); return Elements[(int)key]; } set { System.Diagnostics.Debug.Assert(key is int); Elements[(int)key] = value; } }
        public JToken this[int element] { get { return Elements[element]; } set { Elements[element] = value; } }
        public int Count() { return Elements.Count; }
        public void Add(JToken o) { Elements.Add(o); }
        public void AddRange(IEnumerable<JToken> o) { Elements.AddRange(o); }
        public void RemoveAt(int index) { Elements.RemoveAt(index); }
        public void Clear() { Elements.Clear(); }
        public JToken Find(System.Predicate<JToken> predicate) { return Elements.Find(predicate); }       // find an entry matching the predicate
        public T Find<T>(System.Predicate<JToken> predicate) { Object r = Elements.Find(predicate); return (T)r; }       // find an entry matching the predicate

        public List<string> String() { return Elements.ConvertAll<string>((o) => { return o.ttype == TType.String ? ((JString)o).Value : null; }); }
        public List<int> Int() { return Elements.ConvertAll<int>((o) => { return (int)((JLong)o).Value; }); }
        public List<long> Long() { return Elements.ConvertAll<long>((o) => { return ((JLong)o).Value; }); }
        public List<double> Double() { return Elements.ConvertAll<double>((o) => { return ((JDouble)o).Value; }); }

        public override IEnumerator<JToken> GetSubClassTokenEnumerator() { return Elements.GetEnumerator(); }
        public override IEnumerator GetSubClassEnumerator() { return Elements.GetEnumerator(); }

        public new static JArray Parse(string s)        // null if failed.
        {
            var res = JToken.Parse(s);
            return res as JArray;
        }

        public new static JArray Parse(string s, out string error, bool checkeol = false)
        {
            var res = JToken.Parse(s, out error, checkeol);
            return res as JArray;
        }
    }

}



