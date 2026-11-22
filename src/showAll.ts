import { useEffect, useState } from "react";

// "Show all Use options": the switch is in the Debug section, the Use list in the game section
const SHOW_ALL_KEY = "multifg:showAllChoices";
const listeners = new Set<(on: boolean) => void>();

function read(): boolean {
  try {
    return localStorage.getItem(SHOW_ALL_KEY) === "1";
  } catch {
    return false;
  }
}

export function useShowAll(): [boolean, (on: boolean) => void] {
  const [on, setOn] = useState(read);
  useEffect(() => {
    listeners.add(setOn);
    return () => {
      listeners.delete(setOn);
    };
  }, []);
  const set = (next: boolean) => {
    try {
      localStorage.setItem(SHOW_ALL_KEY, next ? "1" : "0");
    } catch {
      // just not remembered
    }
    listeners.forEach((l) => l(next));
  };
  return [on, set];
}
