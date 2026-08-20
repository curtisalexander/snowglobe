import { spawn } from "node:child_process";

const maximumOutputBytes = 4096;

export async function runProcess(
  command: string,
  args: string[],
  stdin: string,
  signal: AbortSignal | undefined,
  timeoutMs: number,
): Promise<string | undefined> {
  return new Promise((resolve) => {
    const child = spawn(command, args, {
      shell: false,
      stdio: ["pipe", "pipe", "pipe"],
    });
    let stdout = Buffer.alloc(0);
    let settled = false;
    let stopped = false;
    let forceKill: NodeJS.Timeout | undefined;

    const finish = (output: string | undefined) => {
      if (settled) return;
      settled = true;
      clearTimeout(timeout);
      if (forceKill) clearTimeout(forceKill);
      signal?.removeEventListener("abort", stop);
      resolve(output);
    };

    const stop = () => {
      if (stopped) return;
      stopped = true;
      child.kill("SIGTERM");
      forceKill = setTimeout(() => child.kill("SIGKILL"), 1000);
    };

    const timeout = setTimeout(stop, timeoutMs);
    if (signal?.aborted) stop();
    else signal?.addEventListener("abort", stop, { once: true });

    child.stdout.on("data", (chunk: Buffer) => {
      if (stdout.length + chunk.length > maximumOutputBytes) {
        stop();
        return;
      }
      stdout = Buffer.concat([stdout, chunk]);
    });
    child.stderr.resume();
    child.on("error", () => finish(undefined));
    child.on("close", (code) => {
      if (code !== 0 || stopped || signal?.aborted) {
        finish(undefined);
        return;
      }
      finish(stdout.toString("utf8").trim());
    });
    child.stdin.on("error", () => undefined);
    child.stdin.end(stdin);
  });
}
