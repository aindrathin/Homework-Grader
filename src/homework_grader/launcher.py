"""A small Java launcher that records when the student's program reads its input.

Students test their programs in a console, where each typed answer appears right
after its prompt. The grader feeds ``input.txt`` through stdin instead, so the
input never appears in the output. To show it where it was typed, the program is
started through this launcher, which:

- hands the program at most one line of input each time it asks for more (as a
  console does when someone presses Enter), and
- writes to a log how many bytes of output had been printed before each read.

The program's output is exactly what it would be without the launcher; grading
still compares only the output. The launcher uses fully qualified names so a
student class named, say, ``String`` or ``Thread`` can't break it.
"""

from __future__ import annotations

from pathlib import Path

LAUNCHER_CLASS = "HomeworkGraderLauncher__"
LAUNCHER_SOURCE = f"""\
// Added by Homework Grader. Not part of the student's submission.
public final class {LAUNCHER_CLASS} {{
    private static long written = 0;
    private static java.io.PrintStream out;
    private static java.io.PrintStream log;

    public static void main(java.lang.String[] args) throws java.lang.Throwable {{
        final java.io.FileOutputStream stdout =
            new java.io.FileOutputStream(java.io.FileDescriptor.out);
        java.io.OutputStream counting = new java.io.OutputStream() {{
            public void write(int b) throws java.io.IOException {{
                stdout.write(b);
                written++;
            }}
            public void write(byte[] b, int off, int len) throws java.io.IOException {{
                stdout.write(b, off, len);
                written += len;
            }}
            public void flush() throws java.io.IOException {{
                stdout.flush();
            }}
        }};
        // Same buffering as Java's own System.out.
        out = new java.io.PrintStream(
            new java.io.BufferedOutputStream(counting, 128),
            true,
            java.nio.charset.StandardCharsets.UTF_8);
        java.lang.System.setOut(out);
        java.lang.String logPath = java.lang.System.getProperty("grader.inputlog");
        if (logPath != null) {{
            log = new java.io.PrintStream(new java.io.FileOutputStream(logPath), true);
        }}
        java.io.InputStream stdin = new java.io.BufferedInputStream(
            new java.io.FileInputStream(java.io.FileDescriptor.in));
        java.lang.System.setIn(new LineAtATime(stdin));
        java.lang.Runtime.getRuntime().addShutdownHook(new java.lang.Thread(() -> out.flush()));

        java.lang.reflect.Method main =
            java.lang.Class.forName(args[0]).getMethod("main", java.lang.String[].class);
        try {{
            main.invoke(null, (java.lang.Object) new java.lang.String[0]);
        }} catch (java.lang.reflect.InvocationTargetException e) {{
            java.lang.Throwable cause = e.getCause();
            hideLauncher(cause);
            throw cause;
        }}
        out.flush();
    }}

    /** Drop the launcher's own stack frames so error messages look like a normal run. */
    private static void hideLauncher(java.lang.Throwable t) {{
        java.lang.StackTraceElement[] trace = t.getStackTrace();
        int keep = trace.length;
        for (int i = 0; i < trace.length; i++) {{
            java.lang.String c = trace[i].getClassName();
            if (c.startsWith("jdk.internal.reflect.") || c.startsWith("java.lang.reflect.")
                    || c.equals("{LAUNCHER_CLASS}")) {{
                keep = i;
                break;
            }}
        }}
        t.setStackTrace(java.util.Arrays.copyOf(trace, keep));
    }}

    private static final class LineAtATime extends java.io.InputStream {{
        private final java.io.InputStream in;

        LineAtATime(java.io.InputStream in) {{
            this.in = in;
        }}

        public int read() throws java.io.IOException {{
            byte[] one = new byte[1];
            return read(one, 0, 1) <= 0 ? -1 : one[0] & 0xff;
        }}

        public int read(byte[] b, int off, int len) throws java.io.IOException {{
            if (len == 0) return 0;
            out.flush();
            long at = written;
            int n = 0;
            while (n < len) {{
                int c = in.read();
                if (c < 0) break;
                b[off + n++] = (byte) c;
                if (c == '\\n') break;
            }}
            if (n == 0) return -1;
            if (log != null) log.println(at + "\\t" + n);
            return n;
        }}

        public int available() {{
            return 0;  // never more than the current line, like a console
        }}
    }}
}}
"""

# (character position in the output, text read there)
Reads = list[tuple[int, str]]


def read_input_log(log_path: Path, output: bytes, input_bytes: bytes) -> Reads:
    """Turn the launcher's log into (position in the normalized output, input text) pairs.

    Reads at the same spot (nothing printed in between) are joined, so a line read
    one byte at a time still shows as one line.
    """
    if not log_path.is_file():
        return []
    grouped: list[tuple[int, bytes]] = []
    used = 0
    for line in log_path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            at, count = (int(x) for x in line.split("\t"))
        except ValueError:
            continue
        piece = input_bytes[used : used + count]
        used += count
        if grouped and grouped[-1][0] == at:
            grouped[-1] = (at, grouped[-1][1] + piece)
        else:
            grouped.append((at, piece))

    reads: Reads = []
    for at, piece in grouped:
        before = output[:at].decode("utf-8", errors="replace").replace("\r\n", "\n")
        text = piece.decode("utf-8", errors="replace").replace("\r\n", "\n").lstrip("﻿")
        if text:
            reads.append((len(before), text))
    return reads
