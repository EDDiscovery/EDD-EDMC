/*
 * Copyright © 2018 EDDiscovery development team
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
using System.Globalization;
using System.Linq;
using System.Text;
using System.Threading.Tasks;

namespace BaseUtils
{
    [System.Diagnostics.DebuggerDisplay("Action {line.Substring(pos)} : ({line})")]
    public class StringParser
    {
        private int pos;        // always left after an operation on the next non space char
        private string line;

        #region Init and basic status

        public StringParser(string l, int p = 0)
        {
            line = l;
            pos = p;
            SkipSpace();
        }

        public int Position { get { return pos; } }
        public string LineLeft { get { return line.Substring(pos); } }
        public bool IsEOL { get { return pos == line.Length; } }
        public int Left { get { return Math.Max(line.Length - pos,0); } }

        #endregion

        #region Character or String related functions

        public bool SkipSpace()
        {
            while (pos < line.Length && char.IsWhiteSpace(line[pos]))
                pos++;

            return pos == line.Length;
        }

        public void MoveOn(int n)       // with skip space
        {
            pos = Math.Min(pos + n, line.Length);
            SkipSpace();
        }

        public void Remove(int n)       // waste N chars
        {
            pos = Math.Min(pos + n, line.Length);
        }

        public char PeekChar()
        {
            return (pos < line.Length) ? line[pos] : ' ';
        }

        public char GetChar(bool skipspace = false)       // minvalue if at EOL.. Default no skip for backwards compat
        {
            if (pos < line.Length)
            {
                char ch = line[pos++];
                if ( skipspace )
                    SkipSpace();
                return ch;
            }
            else
                return char.MinValue;
        }

        public bool IsChar(char t)
        {
            return pos < line.Length && line[pos] == t;
        }

        public bool IsNextChar(char t)
        {
            return (pos+1) < line.Length && line[pos+1] == t;
        }

        public bool IsCharOneOf(string t)   // any char in t is acceptable in second pos
        {
            return pos < line.Length && t.Contains(line[pos]);
        }

        public bool IsNextCharOneOf(string t)   // any char in t is acceptable in second pos
        {
            return (pos + 1) < line.Length && t.Contains(line[pos + 1]);
        }

        public bool IsLetter()
        {
            return pos < line.Length && char.IsLetter(line[pos]);
        }

        public bool IsLetterUnderscore()
        {
            return pos < line.Length && (char.IsLetter(line[pos]) || line[pos] == '_');
        }

        public bool IsDigit()
        {
            return pos < line.Length && (char.IsDigit(line[pos]));
        }

        public bool IsLetterOrDigit()
        {
            return pos < line.Length && (char.IsLetterOrDigit(line[pos]));
        }

        public bool IsString(string s, StringComparison sc = StringComparison.InvariantCulture)
        {
            return line.Substring(pos).StartsWith(s, sc);
        }

        public bool IsStringMoveOn(string s, StringComparison sc = StringComparison.InvariantCulture, bool skipspace = true)
        {
            if (line.Substring(pos).StartsWith(s, sc))
            {
                pos += s.Length;
                if (skipspace)
                    SkipSpace();
                return true;
            }
            else
                return false;
        }

        public bool IsCharMoveOn(char t, bool skipspace = true)
        {
            if (pos < line.Length && line[pos] == t)
            {
                pos++;
                if (skipspace)
                    SkipSpace();
                return true;
            }
            else
                return false;
        }

        public bool IsCharOneOfMoveOn(string t, bool skipspace = true)   // any char in t is acceptable, then move
        {
            if (pos < line.Length && t.Contains(line[pos]))
            {
                pos++;
                if (skipspace)
                    SkipSpace();
                return true;
            }
            else
                return false;
        }

        public bool IsCharMoveOnOrEOL(char t) // if at EOL, or separ is space (space is auto removed so therefore okay) or separ (and move)
        {
            return IsEOL || t == ' ' || IsCharMoveOn(t);       
        }

        public bool SkipUntil(char[] chars)
        {
            while (pos < line.Length && Array.IndexOf(chars, line[pos]) == -1)
                pos++;

            return pos < line.Length;
        }

        #endregion

        #region WORDs bare or quoted

        // WORD defined by terminators. options to lowercase it and de-escape it

        public string NextWord(string terminators = " ", System.Globalization.CultureInfo lowercase = null, bool replacescape = false)
        {
            if (pos >= line.Length)     // null if there is nothing..
                return null;
            else
            {
                int start = pos;

                while (pos < line.Length && terminators.IndexOf(line[pos]) == -1)
                    pos++;

                string ret = line.Substring(start, pos - start);

                SkipSpace();

                if (lowercase != null)
                    ret = ret.ToLower(lowercase);

                return (replacescape) ? ret.ReplaceEscapeControlChars() : ret;
            }
        }

        // WORD terminated by user test

        public string NextWord(Func<char,bool> test, System.Globalization.CultureInfo lowercase = null, bool replacescape = false)
        {
            if (pos >= line.Length)     // null if there is nothing..
                return null;
            else
            {
                int start = pos;

                while (pos < line.Length && test(line[pos]))
                    pos++;

                string ret = line.Substring(start, pos - start);

                SkipSpace();

                if (lowercase != null)
                    ret = ret.ToLower(lowercase);

                return (replacescape) ? ret.ReplaceEscapeControlChars() : ret;
            }
        }

        // NextWord Invariant

        public string NextWordLCInvariant(string terminators = " ", bool replaceescape = false)
        {
            return NextWord(terminators, lowercase: System.Globalization.CultureInfo.InvariantCulture, replacescape:replaceescape);
        }

        // NextWord with a fixed space comma (or other) terminator.  Fails if not a separ list

        public string NextWordComma(System.Globalization.CultureInfo lowercase = null, bool replaceescape = false, char separ = ',')
        {
            string res = NextWord(" " + separ, lowercase, replaceescape);
            return IsCharMoveOnOrEOL(separ) ? res : null;
        }

        public string NextWordCommaLCInvariant(bool replaceescape = false, char separ = ',')    // nicer quicker way to specify
        {
            return NextWordComma(System.Globalization.CultureInfo.InvariantCulture, replaceescape, separ);
        }

        // Take a " or ' quoted string, or a WORD defined by terminators. options to lowercase it and de-escape it

        public string NextQuotedWord(string nonquoteterminators = " ", System.Globalization.CultureInfo lowercase = null, bool replaceescape = false)
        {
            if (pos < line.Length)
            {
                if (line[pos] == '"' || line[pos] == '\'')
                {
                    char quote = line[pos++];

                    string ret = "";
                    
                    while (true)
                    {
                        int nextslash = line.IndexOf("\\", pos);
                        int nextquote = line.IndexOf(quote, pos);

                        if (nextslash >= 0 && nextslash < nextquote)        // slash first..
                        {
                            if (nextslash + 1 >= line.Length)               // slash at end of line, uhoh
                                return null;

                            if (line[nextslash + 1] == quote)                 // if \", its just a "
                                ret += line.Substring(pos, nextslash - pos) + quote; // copy up to slash, but not the slash, then add the quote
                            else
                                ret += line.Substring(pos, nextslash + 2 - pos);    // copy all, include the next char

                            pos = nextslash + 2;                        // and skip over the slash and the next char
                        }
                        else if (nextquote == -1)                     // must have a quote somewhere..
                            return null;
                        else
                        {
                            ret += line.Substring(pos, nextquote - pos);    // quote, end of line, copy up and remove it
                            pos = nextquote + 1;
                            SkipSpace();

                            if (lowercase != null)
                                ret = ret.ToLower(lowercase);

                            return (replaceescape) ? ret.ReplaceEscapeControlChars() : ret;
                        }
                    }
                }
                else
                    return NextWord(nonquoteterminators, lowercase, replaceescape);
            }
            else
                return null;
        }

        // NextQuotedWord with a fixed space comma terminator.  Fails if not a comma separ list

        public string NextQuotedWordComma(System.Globalization.CultureInfo lowercase = null, bool replaceescape = false, char separ = ',' )           // comma separ
        {
            string res = NextQuotedWord(" " + separ, lowercase, replaceescape);
            return IsCharMoveOnOrEOL(separ) ? res : null;
        }

        // if quoted, take the quote string, else take the rest, space stripped.

        public string NextQuotedWordOrLine(System.Globalization.CultureInfo lowercase = null, bool replaceescape = false)
        {
            if (pos < line.Length)
            {
                if (line[pos] == '"' || line[pos] == '\'')
                    return NextQuotedWord("", lowercase, replaceescape);
                else
                {
                    string ret = line.Substring(pos).Trim();
                    pos = line.Length;

                    if (lowercase != null)
                        ret = ret.ToLower(lowercase);

                    return (replaceescape) ? ret.ReplaceEscapeControlChars() : ret;
                  }
            }
            else
                return null;
        }

        #endregion

        #region List of quoted words

        // Read a list of optionally quoted strings, seperated by separ char.  Stops at EOL or on error.  Check IsEOL if you care about an Error

        public List<string> NextQuotedWordListSepar(System.Globalization.CultureInfo lowercase = null, bool replaceescape = false, char separ = ',')
        {
            List<string> list = new List<string>();

            string r;
            while ((r = NextQuotedWordComma(lowercase, replaceescape, separ)) != null)
            {
                list.Add(r);
            }

            return list;
        }

        // Read a quoted word list off, supporting multiple separ chars, and with multiple other terminators, and the lowercard/replaceescape options
        // null list on error
        public List<string> NextQuotedWordList(System.Globalization.CultureInfo lowercase = null, bool replaceescape = false , 
                                        string separchars = ",", string otherterminators = " ", bool separoptional = false)
        {
            List<string> ret = new List<string>();

            do
            {
                string v = NextQuotedWord(separchars + otherterminators,lowercase,replaceescape);
                if (v == null)
                    return null;

                ret.Add(v);

                if (separoptional)  // if this is set, we these are optional and if not present won't bork it.
                {
                    IsCharOneOfMoveOn(separchars);   // remove it if its there
                }
                else if (!IsEOL && !IsCharOneOfMoveOn(separchars))   // either not EOL, or its not a terminator, fail
                    return null;

            } while (!IsEOL);

            return ret;
        }

        // Read a quoted word list off, with a ) termination

        public List<string> NextOptionallyBracketedList()       // empty list on error
        {
            List<string> sl = new List<string>();
            if (pos < line.Length)
            {
                if (IsCharMoveOn('('))  // if (, we go multi bracketed
                {
                    while (true)
                    {
                        string s = NextQuotedWord("), ");
                        if (s == null) // failed to get a word, error
                        {
                            sl.Clear();
                            break;
                        }
                        else
                            sl.Add(s);

                        if (IsCharMoveOn(')'))      // ), end of word list, move over and stop
                            break;
                        else if (!IsCharMoveOn(','))    // must be ,
                        {
                            sl.Clear();     // cancel list and stop, error
                            break;
                        }
                    }
                }
                else
                {
                    string s = NextQuotedWord("), ");
                    if (s != null)
                        sl.Add(s);
                }
            }

            return sl;
        }

        #endregion

        #region optional Brackets quoted word... word or "word" or ( ("group of words" txt "words" txt ) ) just like a c# expression

        // returns a tuple list, bool = true if string, false if text 
        public List<Tuple<string,bool>> NextOptionallyBracketedQuotedWords(System.Globalization.CultureInfo lowercase = null, bool replacescape = false)       // null in error
        {
            if (pos < line.Length)
            {
                if (IsCharMoveOn('('))  // if (, we go multi bracketed
                {
                    List<Tuple<string, bool>> slist = new List<Tuple<string, bool>>();
                    string acc = "";
                    int bracketlevel = 1;

                    while (pos < line.Length)
                    {
                        if (line[pos] == '"' || line[pos] == '\'')
                        {
                            if (acc.Length > 0)
                            {
                                slist.Add(new Tuple<string, bool>(acc, false));
                                acc = "";
                            }

                            string s = NextQuotedWord(lowercase: lowercase, replaceescape: replacescape);
                            if (s == null)
                                return null;

                            slist.Add(new Tuple<string, bool>(s, true));
                        }
                        else if (IsCharMoveOn(')'))
                        {
                            if (--bracketlevel == 0)
                            {
                                if (acc.Length > 0)
                                    slist.Add(new Tuple<string, bool>(acc, false));
                                return slist;
                            }
                        }
                        else if (IsCharMoveOn('('))
                        {
                            bracketlevel++;
                        }
                        else
                            acc += line[pos++];
                    }
                }
                else
                {
                    string s = NextQuotedWord(lowercase: lowercase, replaceescape: replacescape);
                    if ( s != null )
                        return new List<Tuple<string,bool>>() { new Tuple<string,bool>(s,true) };
                }
            }

            return null;
        }

        #endregion

        #region Numbers and Bools

        public bool? NextBool(string terminators = " ")
        {
            string s = NextWord(terminators);
            return s?.InvariantParseBoolNull();
        }

        public bool? NextBoolComma(string terminators = " ", char separ = ',')
        {
            bool? res = NextBool(terminators);
            return IsCharMoveOnOrEOL(separ) ? res : null;
        }

        public double? NextDouble(string terminators = " ")
        {
            string s = NextWord(terminators);
            return s?.InvariantParseDoubleNull();
        }

        public double? NextDoubleInclusiveTest()        // using a positive test. Not changing original negative test for compatibility
        {
            string s = NextWord((c) => { return char.IsDigit(c) || c == '.' || c == 'e' || c == 'E' || c == '+' || c == '-'; });
            return s?.InvariantParseDoubleNull();
        }

        public object NextLongOrDouble()        // using a positive test, give back a long or a double.
        {
            string s = NextWord((c) => { return char.IsDigit(c) || c == '.' || c == 'e' || c == 'E' || c == '+' || c == '-'; });
            if (s.IndexOfAny(new char[] { '.', 'e', 'E', '+' })>=0)
                return s?.InvariantParseDoubleNull();
            else
                return s?.InvariantParseLongNull();
        }

        public double NextDouble(double def, string terminators = " ")
        {
            string s = NextWord(terminators);
            double? v = s?.InvariantParseDoubleNull();
            return v ?? def;
        }

        public double? NextDoubleComma(string terminators = " ", char separ = ',')
        {
            double? res = NextDouble(terminators);
            return IsCharMoveOnOrEOL(separ) ? res : null;
        }

        public int? NextInt(string terminators = " ")
        {
            string s = NextWord(terminators);
            return s?.InvariantParseIntNull();
        }

        public int NextInt(int def, string terminators = " ")
        {
            string s = NextWord(terminators);
            int? v = s?.InvariantParseIntNull();
            return v ?? def;
        }

        public int? NextIntComma(string terminators = " ", char separ = ',')
        {
            int? res = NextInt(terminators);
            return IsCharMoveOnOrEOL(separ) ? res : null;
        }

        public long? NextLong(string terminators = " ")
        {
            string s = NextWord(terminators);
            return s?.InvariantParseLongNull();
        }

        public long NextLong(long def, string terminators = " ")
        {
            string s = NextWord(terminators);
            long? v = s?.InvariantParseLongNull();
            return v ?? def;
        }

        public long? NextLongComma(string terminators = " ", char separ = ',')
        {
            long? res = NextLong(terminators);
            return IsCharMoveOnOrEOL(separ) ? res : null;
        }

        public DateTime? NextDateTime(CultureInfo ci , DateTimeStyles ds = DateTimeStyles.AssumeUniversal | DateTimeStyles.AdjustToUniversal, string terminators = " ")
        {
            string s = NextQuotedWord(terminators);
            if (s != null && DateTime.TryParse(s, ci, ds, out DateTime ret))
            {
                return ret;
            }
            else
                return null;
        }

        #endregion

        #region Converters for evaluations

        // 
        // Summary:
        //      Reads a int or fp.  Null if error. Skipped space at end to next if valid return
        //

        public Object ConvertNumber(int baseof = 10, bool allowfp = false)     
        {
            bool prefix = false;
            if (IsStringMoveOn("0x", skipspace: false))
            {
                baseof = 16;
                prefix = true;
            }
            else if (IsCharMoveOn('%', skipspace: false))
            {
                baseof = 2;
                prefix = true;
            }
            else if (IsCharMoveOn('`', skipspace: false))
            {
                baseof = 10;
                prefix = true;
            }
            else if (IsChar('0') && IsNextCharOneOf("01234567"))
            {
                baseof = 8;
                pos++;      // waste first 0
            }

            long v = 0;

            int initpos = pos;

            if (baseof == 16)
            {
                int? n;

                while (pos < line.Length && (n = line[pos].ToHex()) != null)
                {
                    v = (v * 16) + n.Value;
                    pos++;
                }
            }
            else
            {
                while (pos < line.Length && line[pos] >= '0' && line[pos] < '0' + baseof)
                {
                    v = (v * baseof) + (line[pos] - '0');
                    pos++;
                }
            }
                
            bool intdigits = initpos != pos;

            if (allowfp && !prefix && ( (IsChar('.') && !IsNextChar('.')) || IsCharOneOf("eE") ))
            {
                bool decimaldigits = false;
                if (IsCharMoveOn('.'))      //X.X, move on and collect
                {
                    while (IsDigit())
                    {
                        pos++;
                        decimaldigits = true;
                    }
                }

                if (intdigits == false && decimaldigits == false)       // must have some sort of digits!
                    return null;

                if (IsCharOneOfMoveOn("eE"))                        // if E..
                {
                    IsCharOneOfMoveOn("+-");                        // opt +/-

                    int epos = pos;
                    while (IsDigit())                               // and digits..
                        pos++;

                    if (epos == pos)                                // no E digits
                        return null;
                }

                string s = line.Substring(initpos, pos - initpos);
                //System.Diagnostics.Debug.WriteLine("Floating Point str " + s);

                double? dres = s.InvariantParseDoubleNull();

                if (dres != null)
                {
                    SkipSpace();
                    return dres.Value;
                }
                else
                    return null;
            }
            else if (initpos != pos)            // long value
            {
                //System.Diagnostics.Debug.WriteLine("Value is " + v + " of " + v.GetType().Name);

                if (IsCharOneOfMoveOn("Ll"))        // UL or LU allowed as prefix for C compatibility.
                {
                    IsCharOneOfMoveOn("uU");
                }
                else if (IsCharOneOfMoveOn("Uu"))
                {
                    IsCharOneOfMoveOn("lL");
                }

                SkipSpace();
                return v;
            }

            return null;
        }

        static public Object ConvertNumber(string s, int baseof = 10, bool allowfp = false) // static version
        {
            StringParser sp = new StringParser(s);
            return sp.ConvertNumber(baseof, allowfp);
        }

        public class ConvertError
        {
            public string ErrorValue { get; private set; }
            public ConvertError(string s) { ErrorValue = s; }
            override public string ToString() => "Error: " + ErrorValue;
        }

        public class ConvertSymbol
        {
            public string SymbolValue { get; private set; }
            public ConvertSymbol(string s) { SymbolValue = s;  }
        }

        // Reads number, "string", symbol, char 'c' or fp. 
        // returns long, string, double, Error or Symbol.  never null

        public Object ConvertNumberStringSymbolChar(int baseof = 10, bool allowfp = false, bool allowstrings = false, bool replaceescape = false, Func<Object> Top = null)
        {
            if (IsCharMoveOn('\'', skipspace: false))    // cannot be spaced..
            {
                if (Left >= 2)
                {
                    long v = line[pos++];
                    if (IsCharMoveOn('\''))         // space skip at end
                        return v;
                }

                return new ConvertError("Incorrectly formatted 'c' expression");
            }
            else if (IsChar('"'))
            {
                if (allowstrings)
                {
                    Object v = NextQuotedWord(replaceescape: replaceescape);

                    if (v == null)
                        return new ConvertError("Missing end quote");
                    else
                    {
                        //System.Diagnostics.Debug.WriteLine("Value is " + v);
                        return v;
                    }
                }
                else
                    return new ConvertError("Strings not supported");
            }
            else if (IsLetterUnderscore())
            {
                string s = NextWord((c) => { return char.IsLetterOrDigit(c) || c=='_'; });

                if (s != null && s.Length > 0)
                {
                    //System.Diagnostics.Debug.WriteLine("Symbol Value is " + s);
                    return new ConvertSymbol(s);
                }
                else
                    return new ConvertError("Missing Symbol/Func Name");
            }
            else
            {
                Object value = ConvertNumber(baseof, allowfp);

                if (value != null)
                    return value;
                else
                    return new ConvertError("Badly formed or missing number");
            }
        }

        static public Object ConvertNumberStringSymbolChar(string s, int baseof = 10, bool allowfp = false, bool allowstrings = false, bool replaceescape = false, Func<Object> Top = null)
        {
            StringParser sp = new StringParser(s);
            return sp.ConvertNumberStringSymbolChar(baseof, allowfp, allowstrings, replaceescape, Top);
        }

        #endregion

        #region Reversing

        public bool ReverseBack( bool quotes = true, bool brackets = true)      // one or both must be true
        {
            System.Diagnostics.Debug.Assert(quotes || brackets);
            int bracketlevel = 0;
            bool inquotes = false;

            while( pos > 0 )
            {
                pos--;
                char c = line[pos];

                if (!inquotes)
                {
                    if (brackets && c == ')')
                    {
                        bracketlevel++;
                    }
                    else if (brackets && c == '(')
                    {
                        bracketlevel--;
                        if (bracketlevel <= 0)
                            return true;
                    }
                    else if (quotes && c == '"')
                    {
                        inquotes = true;
                    }
                }
                else if (quotes && c == '"')
                {
                    if ( pos>0 && line[pos-1] != '\\')
                    {
                        inquotes = !inquotes;

                        if (!inquotes && bracketlevel == 0)
                            return true;
                    }
                }
            }

            return false;
        }

        #endregion

        #region Find

        // Move pointer to string if found

        public bool Find(string s)      // move position to string, this will be the next read..
        {
            int indexof = line.IndexOf(s, pos);
            if (indexof != -1)
                pos = indexof;
            return (indexof != -1);
        }

        // Static wrappers

        public static string FirstQuotedWord(string s, string limits, string def = "", string prefix = "", string postfix = "")
        {
            if (s != null)
            {
                StringParser k1 = new StringParser(s);
                return prefix + k1.NextQuotedWord(limits) + postfix;
            }
            else
                return def;
        }

        public static List<string> ParseWordList(string s, System.Globalization.CultureInfo lowercase = null, bool replaceescape = false, char separ = ',')
        {
            StringParser sp = new StringParser(s);
            return sp.NextQuotedWordListSepar(lowercase, replaceescape, separ);
        }

        #endregion

    }
}
