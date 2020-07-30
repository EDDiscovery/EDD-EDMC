/*
 * Copyright © 2018-2020 EDDiscovery development team
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
using System.Linq;
using System.Text;

namespace BaseUtils
{
    // Quicker version of StringParser.

    [System.Diagnostics.DebuggerDisplay("Action {new string(line,pos,line.Length-pos)} : ({new string(line,0,line.Length)})")]
    public class StringParser2
    {
        private int pos;        // always left after an operation on the next non space char
        private char[] line;

        #region Init and basic status

        public StringParser2(string l, int p = 0)
        {
            line = l.ToCharArray();
            pos = p;
            SkipSpace();
        }

        public int Position { get { return pos; } }
        public string Line { get { return new string(line, 0, line.Length); } }
        public string LineLeft { get { return new string(line, pos, line.Length - pos); } }
        public bool IsEOL { get { return pos == line.Length; } }
        public int Left { get { return Math.Max(line.Length - pos, 0); } }

        #endregion

        #region Character or String related functions

        public void SkipSpace()
        {
            while (pos < line.Length && char.IsWhiteSpace(line[pos]))
                pos++;
        }

        public void SkipCharAndSkipSpace()
        {
            pos++;
            while (pos < line.Length && char.IsWhiteSpace(line[pos]))
                pos++;
        }

        public char PeekChar()
        {
            return (pos < line.Length) ? line[pos] : ' ';
        }


        public char GetChar()       // minvalue if at EOL.. Default no skip for backwards compat
        {
            return (pos < line.Length) ? line[pos++] : ' ';
        }

        public char GetChar(bool skipspace)       // minvalue if at EOL.. Default no skip for backwards compat
        {
            if (pos < line.Length)
            {
                char ch = line[pos++];
                if (skipspace)
                    SkipSpace();
                return ch;
            }
            else
                return char.MinValue;
        }

        public bool IsStringMoveOn(string s)
        {
            for (int i = 0; i < s.Length; i++)
            {
                if (line[pos + i] != s[i])
                    return false;
            }

            pos += s.Length;
            SkipSpace();

            return true;
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

        public void BackUp()
        {
            pos--;
        }


        #endregion

        #region WORDs bare

        // Your on a " or ' quoted string, extract it

        private static char[] buffer = new char[16384];

        public string NextQuotedWordString(char quote, bool replaceescape = false)
        {
            int bpos = 0;

            while (true)
            {
                if (pos == line.Length)  // if reached end of line, error
                {
                    return null;
                }
                else if (line[pos] == quote)        // if reached quote, end of string
                {
                    pos++; //skip end quote

                    while (pos < line.Length && char.IsWhiteSpace(line[pos]))   // skip spaces
                        pos++;

                    return new string(buffer, 0, bpos);
                }
                else if (line[pos] == '\\' && pos < line.Length - 1) // 2 chars min
                {
                    pos++;
                    char esc = line[pos++];     // grab escape and move on

                    if (esc == quote)
                    {
                        buffer[bpos++] = esc;      // place in the character
                    }
                    else if (replaceescape)
                    {
                        switch (esc)
                        {
                            case '\\':
                                buffer[bpos++] = '\\';
                                break;
                            case '/':
                                buffer[bpos++] = '/';
                                break;
                            case 'b':
                                buffer[bpos++] = '\b';
                                break;
                            case 'f':
                                buffer[bpos++] = '\f';
                                break;
                            case 'n':
                                buffer[bpos++] = '\n';
                                break;
                            case 'r':
                                buffer[bpos++] = '\r';
                                break;
                            case 't':
                                buffer[bpos++] = '\t';
                                break;
                            case 'u':
                                if (pos < line.Length - 4)
                                {
                                    int? v1 = line[pos++].ToHex();
                                    int? v2 = line[pos++].ToHex();
                                    int? v3 = line[pos++].ToHex();
                                    int? v4 = line[pos++].ToHex();
                                    if (v1 != null && v2 != null && v3 != null && v4 != null)
                                    {
                                        char c = (char)((v1 << 12) | (v2 << 8) | (v3 << 4) | (v4 << 0));
                                        buffer[bpos++] = c;
                                    }
                                }
                                break;
                        }
                    }
                }
                else
                    buffer[bpos++] = line[pos++];
            }
        }


        #endregion

        #region Numbers and Bools

        static char[] decchars = new char[] { '.', 'e', 'E', '+', '-' };

        public JToken NextJValue(bool sign)     // must be on a digit
        {
            ulong ulv = 0;
            bool bigint = false;
            int start = pos;

            while (true)
            {
                if (pos == line.Length)         // if at end, return as ulong
                {
                    if (bigint)
                    {
                        string part = new string(line, start, pos - start);    // get double string

                        if (System.Numerics.BigInteger.TryParse(part, System.Globalization.NumberStyles.Float, System.Globalization.CultureInfo.InvariantCulture, out System.Numerics.BigInteger bv))
                            return new JBigInteger(sign ? -bv : bv);
                        else
                            return null;
                    }
                    else if (pos == start)      // no chars read
                        return null;
                    else if (ulv <= long.MaxValue)
                        return new JLong(sign ? -(long)ulv : (long)ulv);
                    else if (sign)
                        return null;
                    else
                        return new JULong(ulv);
                }
                else if (line[pos] < '0' || line[pos] > '9')        // if at end of integer..
                {
                    if (line[pos] == '.' || line[pos] == 'E' || line[pos] == 'e')  // if we have gone into a decimal, collect the string and return
                    {
                        while (pos < line.Length && ((line[pos] >= '0' && line[pos] <= '9') || decchars.Contains(line[pos])))
                            pos++;

                        string part = new string(line, start, pos - start);    // get double string

                        while (pos < line.Length && char.IsWhiteSpace(line[pos]))   // skip spaces
                            pos++;

                        if (double.TryParse(part, System.Globalization.NumberStyles.Float, System.Globalization.CultureInfo.InvariantCulture, out double dv))
                            return new JDouble(sign ? -dv : dv);
                        else
                            return null;
                    }
                    else if (bigint)
                    {
                        string part = new string(line, start, pos - start);    // get double string

                        if (System.Numerics.BigInteger.TryParse(part, System.Globalization.NumberStyles.Float, System.Globalization.CultureInfo.InvariantCulture, out System.Numerics.BigInteger bv))
                            return new JBigInteger(sign ? -bv : bv);
                        else
                            return null;
                    }
                    else
                    {
                        if (pos == start)   // this means no chars, caused by a - nothing
                            return null;

                        while (pos < line.Length && char.IsWhiteSpace(line[pos]))   // skip spaces
                            pos++;

                        if (ulv <= long.MaxValue)
                            return new JLong(sign ? -(long)ulv : (long)ulv);
                        else if (sign)
                            return null;
                        else
                            return new JULong(ulv);
                    }
                }
                else
                {
                    if (ulv > ulong.MaxValue / 10)  // if going to overflow, bit int. collect all ints
                        bigint = true;

                    ulv = (ulv * 10) + (ulong)(line[pos++] - '0');
                }
            }
        }

        #endregion

    }
}
