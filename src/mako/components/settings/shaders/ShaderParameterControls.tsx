import { useEffect, useMemo, useState } from "react";
import {
  Dropdown,
  Field,
  SliderField,
  TextField,
  ToggleField,
} from "@decky/ui";
import type { ShaderParameter } from "../../../api/makoApi";
import t from "../../../i18n/i18n";
import { MakoFocusable } from "../../MakoUi";
import {
  shaderColorPreview,
  shaderControlSections,
  shaderNumericValue,
  shaderSliderRange,
  shaderSliderValue,
  type ShaderControlGroup,
} from "./shaderControls";

const transparencyBackground =
  "repeating-conic-gradient(#55616e 0% 25%, #26313c 0% 50%) 0 / 12px 12px";

function ColorSwatches({
  groups,
  selected,
  onSelect,
}: {
  groups: ShaderControlGroup[];
  selected: string;
  onSelect: (key: string) => void;
}) {
  const [focused, setFocused] = useState<string | null>(null);
  return (
    <MakoFocusable
      flow-children="grid"
      noFocusRing
      style={{
        display: "grid",
        gridTemplateColumns: "repeat(4, minmax(0, 1fr))",
        gap: 8,
        marginBottom: 16,
      }}
    >
      {groups.map((group) => (
        <MakoFocusable
          key={group.key}
          role="button"
          tabIndex={0}
          aria-label={group.label}
          aria-pressed={selected === group.key}
          onClick={() => onSelect(group.key)}
          onActivate={() => onSelect(group.key)}
          onKeyDown={(event) => {
            if (event.key !== "Enter" && event.key !== " ") return;
            event.preventDefault();
            event.stopPropagation();
            onSelect(group.key);
          }}
          onFocus={() => setFocused(group.key)}
          onGamepadFocus={() => setFocused(group.key)}
          onBlur={() => setFocused((key) => (key === group.key ? null : key))}
          onGamepadBlur={() =>
            setFocused((key) => (key === group.key ? null : key))
          }
          noFocusRing
          style={{
            minWidth: 0,
            padding: 4,
            border: `2px solid ${selected === group.key ? "#83bff0" : "#444c56"}`,
            borderRadius: 4,
            background: "#18212b",
            outline: focused === group.key ? "2px solid #edf8fb" : "none",
            outlineOffset: 2,
            cursor: "pointer",
          }}
        >
          <div
            aria-hidden="true"
            style={{ background: transparencyBackground }}
          >
            <div
              style={{
                height: 26,
                background: shaderColorPreview(group.parameters),
              }}
            />
          </div>
          <div
            style={{
              marginTop: 4,
              color: "#edf8fb",
              fontSize: 11,
              lineHeight: "14px",
              overflowWrap: "anywhere",
              textAlign: "center",
            }}
          >
            {group.label}
          </div>
        </MakoFocusable>
      ))}
    </MakoFocusable>
  );
}

function NumericParameter({
  parameter,
  onCommit,
  showLabel = true,
}: {
  parameter: ShaderParameter;
  onCommit: (value: number) => void;
  showLabel?: boolean;
}) {
  const displayedValue = shaderNumericValue(parameter.value, parameter.type);
  const [draft, setDraft] = useState(String(displayedValue));
  useEffect(() => setDraft(String(displayedValue)), [displayedValue]);
  const commit = () => {
    const value = Number(draft);
    if (draft.trim() && Number.isFinite(value) && value !== displayedValue)
      onCommit(value);
    else setDraft(String(displayedValue));
  };
  return (
    <TextField
      label={showLabel ? parameter.label : undefined}
      aria-label={parameter.label}
      value={draft}
      onChange={(e) => setDraft(e.target.value)}
      onBlur={commit}
      onKeyDown={(e) => {
        if (e.key === "Enter") commit();
      }}
    />
  );
}

function ParameterControl({
  parameter: p,
  color,
  onChange,
}: {
  parameter: ShaderParameter;
  color: boolean;
  onChange: (values: Record<string, number>) => void;
}) {
  const set = (value: number) => {
    if (Number.isFinite(value)) onChange({ [p.key]: value });
  };
  if (p.type === "bool")
    return (
      <ToggleField
        label={p.label}
        checked={p.value !== 0}
        onChange={(value) => set(value ? 1 : 0)}
      />
    );
  if (
    (p.type === "int" || p.type === "uint") &&
    p.items.length &&
    Number.isInteger(p.value) &&
    p.value >= 0 &&
    p.value < p.items.length
  )
    return (
      <Field label={p.label} childrenLayout="below">
        <Dropdown
          selectedOption={p.value}
          rgOptions={p.items.map((label, data) => ({
            label: label || String(data),
            data,
          }))}
          onChange={(option) => set(Number(option.data))}
        />
      </Field>
    );
  const range = shaderSliderRange(p, color);
  return (
    <>
      {range && (
        <SliderField
          label={`${p.label}: ${shaderNumericValue(p.value, p.type)}`}
          value={Math.max(range.min, Math.min(range.max, p.value))}
          {...range}
          validValues="steps"
          minimumDpadGranularity={range.step}
          onChange={(value) => set(shaderSliderValue(value, range))}
        />
      )}
      <NumericParameter parameter={p} onCommit={set} showLabel={!range} />
    </>
  );
}

export function ShaderParameterControls({
  parameters,
  onChange,
  onBeforeSelectColor,
}: {
  parameters: ShaderParameter[];
  onChange: (values: Record<string, number>) => void;
  onBeforeSelectColor: () => void;
}) {
  const sections = useMemo(
    () => shaderControlSections(parameters),
    [parameters],
  );
  const [selectedColors, setSelectedColors] = useState<Record<string, string>>(
    {},
  );
  const colorLabels = [
    t("SHADER_EDITOR_RED", "Red"),
    t("SHADER_EDITOR_GREEN", "Green"),
    t("SHADER_EDITOR_BLUE", "Blue"),
    t("SHADER_EDITOR_ALPHA", "Alpha"),
  ];
  return (
    <>
      {sections.map((section, index) => {
        const first = section[0];
        const group =
          section.find((item) => item.key === selectedColors[first.key]) ??
          first;
        return (
          <div key={first.key} style={{ marginTop: 16 }}>
            {group.category &&
              group.category !== sections[index - 1]?.[0].category && (
                <div style={{ color: "#aebac6", margin: "12px 0" }}>
                  {group.category}
                </div>
              )}
            {section.length > 1 && (
              <ColorSwatches
                groups={section}
                selected={group.key}
                onSelect={(key) => {
                  if (key === group.key) return;
                  onBeforeSelectColor();
                  setSelectedColors((current) => ({
                    ...current,
                    [first.key]: key,
                  }));
                }}
              />
            )}
            <div key={group.key}>
              {group.parameters.length > 1 && (
                <div style={{ fontWeight: 600, marginBottom: 8 }}>
                  {group.label}
                </div>
              )}
              {group.description && (
                <div
                  style={{
                    color: "#aebac6",
                    fontSize: 12,
                    lineHeight: "16px",
                    marginBottom: 8,
                  }}
                >
                  {group.description}
                </div>
              )}
              {group.color && (
                <>
                  <div
                    role="img"
                    aria-label={t(
                      "SHADER_EDITOR_COLOR_PREVIEW",
                      "Colour preview",
                    )}
                    style={{
                      height: 32,
                      marginBottom: 8,
                      border: "1px solid #8393a5",
                      background: transparencyBackground,
                    }}
                  >
                    <div
                      style={{
                        height: "100%",
                        background: shaderColorPreview(group.parameters),
                      }}
                    />
                  </div>
                  {group.parameters.some((p) => p.value < 0 || p.value > 1) && (
                    <div
                      style={{
                        color: "#aebac6",
                        fontSize: 12,
                        marginBottom: 8,
                      }}
                    >
                      {t(
                        "SHADER_EDITOR_COLOR_RANGE",
                        "Preview is limited to 0–1. Exact values are preserved.",
                      )}
                    </div>
                  )}
                </>
              )}
              <div
                style={{ display: "flex", flexDirection: "column", gap: 16 }}
              >
                {group.parameters.map((p, component) => (
                  <div
                    key={p.key}
                    className="mako-shader-parameter"
                    style={{
                      display: "flex",
                      flexDirection: "column",
                      gap: 10,
                      minWidth: 0,
                    }}
                  >
                    <ParameterControl
                      parameter={{
                        ...p,
                        label:
                          group.parameters.length > 1
                            ? group.color
                              ? colorLabels[component]
                              : ["X", "Y", "Z", "W"][component]
                            : p.label,
                      }}
                      color={group.color}
                      onChange={onChange}
                    />
                  </div>
                ))}
              </div>
            </div>
          </div>
        );
      })}
    </>
  );
}
