import type { AnrJob, Fsr4Job, HelixJob, OptiJob } from "./api";

export type UpdateJobs = {
  opti?: OptiJob | null;
  helix?: HelixJob | null;
  fsr4?: Fsr4Job | null;
  anr?: AnrJob | null;
};

export type BatchName = "OptiScaler" | "HelixSR" | "FSR4 Injector" | "ANR FG" | "MAKO";

const ratio = (a?: number | null, b?: number | null) => (a && b ? Math.min(1, a / b) : 0);

// How far one backend's update is (0..1) and what it is doing, from its install job
export function backendProgress(name: BatchName, jobs: UpdateJobs): { fraction: number; stage: string } {
  switch (name) {
    case "OptiScaler": {
      const j = jobs.opti;
      if (!j) return { fraction: 0, stage: "starting" };
      if (j.state !== "running") return { fraction: 1, stage: j.state === "failed" ? "failed" : "done" };
      return j.phase === "download"
        ? { fraction: 0.8 * ratio(j.downloaded, j.size), stage: "downloading" }
        : { fraction: 0.9, stage: "installing" };
    }
    case "HelixSR": {
      const j = jobs.helix;
      if (!j) return { fraction: 0, stage: "starting" };
      if (j.state !== "running") return { fraction: 1, stage: j.state === "failed" ? "failed" : "done" };
      if (j.phase === "download") return { fraction: 0.3 * ratio(j.downloaded, j.size), stage: "downloading" };
      if (j.phase !== "setup") return { fraction: 0.32, stage: j.phase === "verify" ? "checking the download" : "unpacking" };
      return {
        fraction: 0.35 + 0.65 * Math.min(1, (j.setup_percent ?? 0) / 100),
        stage: j.setup_step ? `setup: ${j.setup_step}` : "setup",
      };
    }
    case "FSR4 Injector": {
      const j = jobs.fsr4;
      if (!j) return { fraction: 0, stage: "starting" };
      if (j.state !== "running") return { fraction: 1, stage: j.state === "failed" ? "failed" : "done" };
      return j.phase === "amd"
        ? { fraction: 0.1 + 0.9 * ratio(j.done, j.total), stage: "downloading AMD's FSR 4 files" }
        : { fraction: 0.05, stage: "downloading" };
    }
    case "ANR FG": {
      const j = jobs.anr;
      if (!j) return { fraction: 0, stage: "starting" };
      if (j.state !== "running") return { fraction: 1, stage: j.state === "failed" ? "failed" : "done" };
      return { fraction: ratio(j.done, j.total), stage: "downloading" };
    }
    case "MAKO":
      return { fraction: 1, stage: "done" };
  }
}

export function jobRunning(name: BatchName, jobs: UpdateJobs): boolean {
  const j = { OptiScaler: jobs.opti, HelixSR: jobs.helix, "FSR4 Injector": jobs.fsr4, "ANR FG": jobs.anr, MAKO: null }[name];
  return j?.state === "running";
}
