import type { ShaderParameter } from "../../../api/makoApi";

export interface ShaderControlGroup {
  key: string;
  label: string;
  description: string;
  category: string;
  color: boolean;
  parameters: ShaderParameter[];
}

// Group only a complete compiler-declared vector. Labels/names never imply type.
export function shaderControlGroups(
  parameters: ShaderParameter[],
): ShaderControlGroup[] {
  const groups: ShaderControlGroup[] = [];
  for (let index = 0; index < parameters.length;) {
    const p = parameters[index];
    const hint = p.presentation;
    let members = [p];
    if (
      hint &&
      p.type !== "bool" &&
      ["", "input", "drag", "slider", "color"].includes(hint.widget) &&
      typeof hint.label === "string" &&
      hint.label.length > 0 &&
      hint.component === 0 &&
      Number.isInteger(hint.count) &&
      hint.count >= 2 &&
      hint.count <= 4 &&
      hint.group === p.key &&
      p.key.endsWith("_0")
    ) {
      const candidates = parameters.slice(index, index + hint.count);
      if (
        candidates.length === hint.count &&
        candidates.every((candidate, component) => {
          const other = candidate.presentation;
          return (
            other &&
            other.group === hint.group &&
            other.label === hint.label &&
            other.widget === hint.widget &&
            other.count === hint.count &&
            other.component === component &&
            candidate.key === hint.group.slice(0, -1) + component &&
            candidate.type === p.type &&
            candidate.label === `${hint.label} [${component + 1}]` &&
            !candidate.items.length &&
            candidate.category === p.category &&
            candidate.description === p.description
          );
        })
      )
        members = candidates;
    }
    const grouped = members.length > 1;
    groups.push({
      key: p.key,
      label: grouped ? hint!.label : p.label,
      description: p.description,
      category: p.category,
      color:
        grouped &&
        members.length >= 3 &&
        p.type === "float" &&
        hint!.widget === "color",
      parameters: members,
    });
    index += members.length;
  }
  return groups;
}

// Keep palette boundaries aligned with Qt's independent presentation binding.
export function shaderControlSections(
  parameters: ShaderParameter[],
): ShaderControlGroup[][] {
  const sections: ShaderControlGroup[][] = [];
  for (const group of shaderControlGroups(parameters)) {
    const previous = sections[sections.length - 1];
    if (
      group.color &&
      previous?.[0].color &&
      previous[0].category === group.category
    )
      previous.push(group);
    else sections.push([group]);
  }
  return sections;
}

// The helper emits FP32 values with nine significant digits. Shorten only
// those readbacks (or exact FP32 numbers), preserving the shader's bits and
// independently typed decimals. This is presentation, never a profile migration.
export function shaderNumericValue(
  value: number,
  type: ShaderParameter["type"],
) {
  if (type !== "float" || !Number.isFinite(value) || value === 0) return value;
  const stored = Math.fround(value);
  if (
    !Number.isFinite(stored) ||
    (value !== stored && value !== Number(stored.toPrecision(9)))
  )
    return value;
  for (let digits = 1; digits <= 9; digits++) {
    const candidate = Number(value.toPrecision(digits));
    if (Math.fround(candidate) === stored) return candidate;
  }
  return value;
}

export function shaderSliderRange(p: ShaderParameter, color = false) {
  if (p.presentation?.widget === "input") return null;
  const min =
    p.min == null ? (color ? 0 : null) : shaderNumericValue(p.min, p.type);
  const max =
    p.max == null ? (color ? 1 : null) : shaderNumericValue(p.max, p.type);
  if (
    min === null ||
    max === null ||
    !Number.isFinite(min) ||
    !Number.isFinite(max) ||
    max <= min
  )
    return null;
  // At least 100 intervals, with decimal steps instead of fractions such as
  // 0.015 for Gamma's 0.5–2 range. Authored steps remain authoritative.
  const step =
    p.step == null
      ? p.type === "float"
        ? 10 **
          Math.floor(Math.log10(Number(((max - min) / 100).toPrecision(15))))
        : 1
      : shaderNumericValue(p.step, p.type);
  if (
    !Number.isFinite(step) ||
    step <= 0 ||
    (p.type !== "float" &&
      (!Number.isInteger(min) ||
        !Number.isInteger(max) ||
        !Number.isInteger(step)))
  )
    return null;
  return { min, max, step };
}

export function shaderSliderValue(
  value: number,
  range: { min: number; max: number; step: number },
) {
  if (!Number.isFinite(value)) return value;
  if (value <= range.min) return range.min;
  if (value >= range.max) return range.max;
  const snapped =
    range.min + Math.round((value - range.min) / range.step) * range.step;
  // Remove JS arithmetic tails, not shader precision. Exact fields bypass this.
  return Math.max(
    range.min,
    Math.min(range.max, Number(snapped.toPrecision(15))),
  );
}

export function shaderColorPreview(parameters: ShaderParameter[]): string {
  const channel = (index: number) =>
    Math.max(0, Math.min(1, parameters[index]?.value ?? 1));
  return `rgba(${[0, 1, 2].map((i) => Math.round(channel(i) * 255)).join(", ")}, ${parameters.length === 4 ? channel(3) : 1})`;
}
