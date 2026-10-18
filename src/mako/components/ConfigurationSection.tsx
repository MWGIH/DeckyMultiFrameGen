import type { ConfigurationEditorProps } from "./settings/types";
import { usePersistentCollapseState } from "../hooks/usePersistentCollapseState";
import { AdvancedRenderingConfigurationGroup } from "./settings/AdvancedRenderingConfigurationGroup";
import { CompatibilityConfigurationGroup } from "./settings/CompatibilityConfigurationGroup";
import { ExternalToolsConfigurationGroup } from "./settings/ExternalToolsConfigurationGroup";
import { ManualOverridesConfigurationGroup } from "./settings/ManualOverridesConfigurationGroup";

export type ConfigurationGroupId =
  "advanced" | "compatibility" | "external-tools" | "manual-overrides";

interface ConfigurationSectionProps extends ConfigurationEditorProps {
  groups?: readonly ConfigurationGroupId[];
  collapsible?: boolean;
}

interface FrameGenerationConfigurationSectionProps extends ConfigurationEditorProps {
  initiallyCollapsed?: boolean;
  collapsible?: boolean;
}

const WORKAROUNDS_COLLAPSED_KEY = "mako-workarounds-collapsed";
const CONFIG_COLLAPSED_KEY = "mako-config-collapsed";
const EXTERNAL_TOOLS_COLLAPSED_KEY = "mako-external-tools-collapsed";
const MANUAL_OVERRIDES_COLLAPSED_KEY = "mako-manual-overrides-collapsed";

const collapseControlStyles = `
  .MAKO_ConfigCollapseButton_Container > div > div > div > button,
  .MAKO_ConfigCollapseButton_Container > div > div > div > div > button,
  .MAKO_WorkaroundsCollapseButton_Container > div > div > div > button,
  .MAKO_ExternalToolsCollapseButton_Container > div > div > div > button,
  .MAKO_ManualOverridesCollapseButton_Container > div > div > div > button {
    height: 10px !important;
  }
  .MAKO_WorkaroundsCollapseButton_Container > div > div > div > div > button,
  .MAKO_ExternalToolsCollapseButton_Container > div > div > div > div > button,
  .MAKO_ManualOverridesCollapseButton_Container > div > div > div > div > button {
    height: 10px !important;
  }
`;

export function FrameGenerationConfigurationSection({
  config,
  onConfigChange,
  onConfigUpdate,
  initiallyCollapsed = true,
  collapsible = true,
}: FrameGenerationConfigurationSectionProps) {
  const [configCollapsed, setConfigCollapsed] = usePersistentCollapseState(
    CONFIG_COLLAPSED_KEY,
    initiallyCollapsed,
    "frame generation advanced settings",
  );

  return (
    <>
      <style>{collapseControlStyles}</style>
      <AdvancedRenderingConfigurationGroup
        config={config}
        onConfigChange={onConfigChange}
        onConfigUpdate={onConfigUpdate}
        collapsed={collapsible && configCollapsed}
        onToggle={
          collapsible ? () => setConfigCollapsed(!configCollapsed) : undefined
        }
      />
    </>
  );
}

export function ConfigurationSection({
  config,
  onConfigChange,
  onConfigUpdate,
  groups = ["advanced", "compatibility", "external-tools", "manual-overrides"],
  collapsible = true,
}: ConfigurationSectionProps) {
  const [workaroundsCollapsed, setWorkaroundsCollapsed] =
    usePersistentCollapseState(WORKAROUNDS_COLLAPSED_KEY, true, "workarounds");
  const [manualOverridesCollapsed, setManualOverridesCollapsed] =
    usePersistentCollapseState(
      MANUAL_OVERRIDES_COLLAPSED_KEY,
      true,
      "manual overrides",
    );
  const [externalToolsCollapsed, setExternalToolsCollapsed] =
    usePersistentCollapseState(
      EXTERNAL_TOOLS_COLLAPSED_KEY,
      true,
      "external tools",
    );

  return (
    <>
      <style>{`${collapseControlStyles}
        .MAKO_ManualOverrideFields {
          display: flex;
          flex-direction: column;
          gap: 12px;
          width: 100%;
          min-width: 0;
          margin: 10px 0 0;
        }
        .MAKO_ManualOverrideFields > * {
          margin-bottom: 0 !important;
        }
        .MAKO_ManualOverrideFields > * + * {
          margin-top: 0 !important;
        }
        .MAKO_GpuDescription {
          display: block;
          padding-bottom: 10px;
        }
      `}</style>

      {groups.includes("advanced") && (
        <FrameGenerationConfigurationSection
          config={config}
          onConfigChange={onConfigChange}
          onConfigUpdate={onConfigUpdate}
          initiallyCollapsed={false}
          collapsible={collapsible}
        />
      )}

      {groups.includes("compatibility") && (
        <CompatibilityConfigurationGroup
          config={config}
          onConfigChange={onConfigChange}
          onConfigUpdate={onConfigUpdate}
          collapsed={collapsible && workaroundsCollapsed}
          onToggle={
            collapsible
              ? () => setWorkaroundsCollapsed(!workaroundsCollapsed)
              : undefined
          }
        />
      )}

      {groups.includes("external-tools") && (
        <ExternalToolsConfigurationGroup
          config={config}
          onConfigChange={onConfigChange}
          collapsed={collapsible && externalToolsCollapsed}
          onToggle={
            collapsible
              ? () => setExternalToolsCollapsed(!externalToolsCollapsed)
              : undefined
          }
        />
      )}

      {groups.includes("manual-overrides") && (
        <ManualOverridesConfigurationGroup
          config={config}
          onConfigChange={onConfigChange}
          collapsed={collapsible && manualOverridesCollapsed}
          onToggle={
            collapsible
              ? () => setManualOverridesCollapsed(!manualOverridesCollapsed)
              : undefined
          }
        />
      )}
    </>
  );
}
