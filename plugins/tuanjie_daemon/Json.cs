// Json.cs — a tiny, dependency-free JSON reader/writer for the connector.
//
// The engine's JsonUtility only (de)serializes concrete [Serializable] types,
// not the arbitrary frames this protocol needs. Rather than pull in a package,
// the connector uses this minimal codec:
//   * Parse: enough of a reader to read the daemon's request frames
//     (objects, strings, numbers) — see JsonValue.
//   * Encode: turns an arbitrary `result` value into JSON, matching the
//     Python connector's contract — JSON-serializable values pass through,
//     anything else falls back to its string form (like Python's repr()).

using System;
using System.Collections;
using System.Collections.Generic;
using System.Globalization;
using System.Text;

namespace DccDaemon
{
    // A parsed JSON object with typed accessors used by the connector.
    public class JsonValue
    {
        private readonly Dictionary<string, object> _map;

        public JsonValue(Dictionary<string, object> map)
        {
            _map = map ?? new Dictionary<string, object>();
        }

        public string GetString(string key)
        {
            return _map.TryGetValue(key, out var v) && v != null ? v.ToString() : null;
        }

        public object GetRaw(string key)
        {
            return _map.TryGetValue(key, out var v) ? v : null;
        }

        public JsonValue GetObject(string key)
        {
            if (_map.TryGetValue(key, out var v) && v is Dictionary<string, object> d)
                return new JsonValue(d);
            return null;
        }
    }

    public static class Json
    {
        // -- parse (only what request frames need) -----------------------

        public static JsonValue Parse(string text)
        {
            try
            {
                int i = 0;
                object value = ParseValue(text, ref i);
                if (value is Dictionary<string, object> map)
                    return new JsonValue(map);
                return null;
            }
            catch
            {
                return null;
            }
        }

        private static object ParseValue(string s, ref int i)
        {
            SkipWhitespace(s, ref i);
            char c = s[i];
            switch (c)
            {
                case '{': return ParseObject(s, ref i);
                case '[': return ParseArray(s, ref i);
                case '"': return ParseString(s, ref i);
                case 't': i += 4; return true;
                case 'f': i += 5; return false;
                case 'n': i += 4; return null;
                default: return ParseNumber(s, ref i);
            }
        }

        private static Dictionary<string, object> ParseObject(string s, ref int i)
        {
            var map = new Dictionary<string, object>();
            i++; // {
            SkipWhitespace(s, ref i);
            if (s[i] == '}') { i++; return map; }
            while (true)
            {
                SkipWhitespace(s, ref i);
                string key = ParseString(s, ref i);
                SkipWhitespace(s, ref i);
                i++; // :
                object value = ParseValue(s, ref i);
                map[key] = value;
                SkipWhitespace(s, ref i);
                if (s[i] == ',') { i++; continue; }
                i++; // }
                break;
            }
            return map;
        }

        private static List<object> ParseArray(string s, ref int i)
        {
            var list = new List<object>();
            i++; // [
            SkipWhitespace(s, ref i);
            if (s[i] == ']') { i++; return list; }
            while (true)
            {
                object value = ParseValue(s, ref i);
                list.Add(value);
                SkipWhitespace(s, ref i);
                if (s[i] == ',') { i++; continue; }
                i++; // ]
                break;
            }
            return list;
        }

        private static string ParseString(string s, ref int i)
        {
            var sb = new StringBuilder();
            i++; // opening quote
            while (s[i] != '"')
            {
                char c = s[i++];
                if (c == '\\')
                {
                    char e = s[i++];
                    switch (e)
                    {
                        case '"': sb.Append('"'); break;
                        case '\\': sb.Append('\\'); break;
                        case '/': sb.Append('/'); break;
                        case 'b': sb.Append('\b'); break;
                        case 'f': sb.Append('\f'); break;
                        case 'n': sb.Append('\n'); break;
                        case 'r': sb.Append('\r'); break;
                        case 't': sb.Append('\t'); break;
                        case 'u':
                            string hex = s.Substring(i, 4);
                            i += 4;
                            sb.Append((char)Convert.ToInt32(hex, 16));
                            break;
                    }
                }
                else
                {
                    sb.Append(c);
                }
            }
            i++; // closing quote
            return sb.ToString();
        }

        private static object ParseNumber(string s, ref int i)
        {
            int start = i;
            while (i < s.Length && "+-0123456789.eE".IndexOf(s[i]) >= 0) i++;
            string token = s.Substring(start, i - start);
            if (token.IndexOf('.') >= 0 || token.IndexOf('e') >= 0 || token.IndexOf('E') >= 0)
                return double.Parse(token, CultureInfo.InvariantCulture);
            return long.Parse(token, CultureInfo.InvariantCulture);
        }

        private static void SkipWhitespace(string s, ref int i)
        {
            while (i < s.Length && char.IsWhiteSpace(s[i])) i++;
        }

        // -- encode (arbitrary result -> JSON, string fallback) ----------

        public static string Encode(object value)
        {
            var sb = new StringBuilder();
            EncodeValue(value, sb, 0);
            return sb.ToString();
        }

        private static void EncodeValue(object value, StringBuilder sb, int depth)
        {
            if (value == null) { sb.Append("null"); return; }

            switch (value)
            {
                case string s:
                    EncodeString(s, sb);
                    return;
                case bool b:
                    sb.Append(b ? "true" : "false");
                    return;
                case float f:
                    sb.Append(f.ToString("R", CultureInfo.InvariantCulture));
                    return;
                case double d:
                    sb.Append(d.ToString("R", CultureInfo.InvariantCulture));
                    return;
                case sbyte _:
                case byte _:
                case short _:
                case ushort _:
                case int _:
                case uint _:
                case long _:
                case ulong _:
                    sb.Append(Convert.ToString(value, CultureInfo.InvariantCulture));
                    return;
            }

            // Guard against pathological nesting / cycles.
            if (depth > 32)
            {
                EncodeString(value.ToString(), sb);
                return;
            }

            if (value is IDictionary dict)
            {
                sb.Append('{');
                bool first = true;
                foreach (DictionaryEntry entry in dict)
                {
                    if (!first) sb.Append(',');
                    first = false;
                    EncodeString(entry.Key?.ToString() ?? "null", sb);
                    sb.Append(':');
                    EncodeValue(entry.Value, sb, depth + 1);
                }
                sb.Append('}');
                return;
            }

            if (value is IEnumerable enumerable && !(value is string))
            {
                sb.Append('[');
                bool first = true;
                foreach (var item in enumerable)
                {
                    if (!first) sb.Append(',');
                    first = false;
                    EncodeValue(item, sb, depth + 1);
                }
                sb.Append(']');
                return;
            }

            // Anything else: fall back to its string form, like Python repr().
            EncodeString(value.ToString(), sb);
        }

        private static void EncodeString(string s, StringBuilder sb)
        {
            sb.Append('"');
            foreach (char c in s)
            {
                switch (c)
                {
                    case '"': sb.Append("\\\""); break;
                    case '\\': sb.Append("\\\\"); break;
                    case '\b': sb.Append("\\b"); break;
                    case '\f': sb.Append("\\f"); break;
                    case '\n': sb.Append("\\n"); break;
                    case '\r': sb.Append("\\r"); break;
                    case '\t': sb.Append("\\t"); break;
                    default:
                        if (c < 0x20)
                            sb.Append("\\u").Append(((int)c).ToString("x4"));
                        else
                            sb.Append(c);
                        break;
                }
            }
            sb.Append('"');
        }
    }
}
