// Runs the Python solver (solver/analyze.py) as a separate process and collects its answer.
// A new process per request means evaluator changes apply on the next F8, with no game restart.
// It runs on a background thread so a slow search can't freeze the game.

using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Globalization;
using System.Threading;

public sealed class BestMove
{
    public int Depth;
    public string Action;
    public int DeckIndex;
    public float Score;
    public string Line;
}

public sealed class SolverResult
{
    public int StateSequence;
    public string Error;
    public string Report = "";
    public string AnalysisJson;
    public string EvaluatorVersion = "unknown";
    public readonly Dictionary<int, BestMove> Best = new Dictionary<int, BestMove>();
}

public sealed class SolverBridge
{
    private const string PythonExecutable = "python";
    private const string SolverScript =
        @"C:\Users\space\Desktop\workspace\shogun-showdown-autoplay\solver\analyze.py";
    private const int TimeoutMilliseconds = 60000;

    private readonly object gate = new object();
    private SolverResult finished;
    private bool busy;

    public bool Busy
    {
        get { lock (gate) { return busy; } }
    }

    public void Start(string stateJson, int stateSequence)
    {
        lock (gate) { busy = true; }
        Thread thread = new Thread(delegate() { Run(stateJson, stateSequence); });
        thread.IsBackground = true;
        thread.Start();
    }

    // Returns the finished result once, or null if there isn't one waiting.
    public SolverResult TakeResult()
    {
        lock (gate)
        {
            SolverResult result = finished;
            finished = null;
            return result;
        }
    }

    private void Run(string stateJson, int stateSequence)
    {
        SolverResult result;
        try
        {
            result = Parse(RunProcess(stateJson));
        }
        catch (Exception ex)
        {
            result = new SolverResult { Error = ex.Message };
        }
        result.StateSequence = stateSequence;
        lock (gate)
        {
            finished = result;
            busy = false;
        }
    }

    private static string RunProcess(string stateJson)
    {
        ProcessStartInfo info = new ProcessStartInfo(PythonExecutable, "\"" + SolverScript + "\"");
        info.UseShellExecute = false;
        info.CreateNoWindow = true;
        info.RedirectStandardInput = true;
        info.RedirectStandardOutput = true;
        info.RedirectStandardError = true;

        using (Process process = Process.Start(info))
        {
            // Read stderr on its own thread so a full pipe can't block the process.
            string errors = "";
            Thread errorReader = new Thread(delegate() { errors = process.StandardError.ReadToEnd(); });
            errorReader.IsBackground = true;
            errorReader.Start();

            string output = null;
            Thread outputReader = new Thread(delegate() { output = process.StandardOutput.ReadToEnd(); });
            outputReader.IsBackground = true;
            outputReader.Start();

            process.StandardInput.Write(stateJson);
            process.StandardInput.Close();

            if (!process.WaitForExit(TimeoutMilliseconds))
            {
                process.Kill();
                throw new Exception("the solver took longer than " + TimeoutMilliseconds / 1000 + " seconds");
            }
            outputReader.Join();
            errorReader.Join();
            if (process.ExitCode != 0) throw new Exception("the solver failed:\n" + errors);
            return output;
        }
    }

    private static SolverResult Parse(string output)
    {
        SolverResult result = new SolverResult();
        const string reportMarker = "REPORT\n";
        string text = output.Replace("\r\n", "\n");
        int reportStart = text.IndexOf(reportMarker, StringComparison.Ordinal);
        if (reportStart < 0) throw new Exception("the solver's answer had no report");
        result.Report = text.Substring(reportStart + reportMarker.Length).TrimEnd();

        foreach (string line in text.Substring(0, reportStart).Split('\n'))
        {
            if (line.StartsWith("BEST ", StringComparison.Ordinal))
            {
                string[] parts = line.Split(new[] { ' ' }, 6);
                BestMove move = new BestMove();
                move.Depth = int.Parse(parts[1], CultureInfo.InvariantCulture);
                move.Action = parts[2];
                move.DeckIndex = int.Parse(parts[3], CultureInfo.InvariantCulture);
                move.Score = float.Parse(parts[4], CultureInfo.InvariantCulture);
                move.Line = parts[5];
                result.Best[move.Depth] = move;
            }
            else if (line.StartsWith("ANALYSIS ", StringComparison.Ordinal))
            {
                result.AnalysisJson = line.Substring("ANALYSIS ".Length).Trim();
            }
            else if (line.StartsWith("VERSION ", StringComparison.Ordinal))
            {
                result.EvaluatorVersion = line.Substring("VERSION ".Length).Trim();
            }
        }
        return result;
    }
}
