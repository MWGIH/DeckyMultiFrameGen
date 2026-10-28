import { Field, PanelSectionRow, ProgressBar } from "@decky/ui";

// Steam's ProgressBarWithInfo squeezes the bar beside its label and runs past the panel's right edge
// in the Quick Access panel, so the text gets its own row and Steam's plain bar the full width below it
export function ProgressRow({
  title,
  percent,
  detail,
}: {
  title: string;
  percent?: number;
  detail?: string | null;
}) {
  return (
    <>
      <PanelSectionRow>
        <Field
          label={title}
          description={detail ?? undefined}
          bottomSeparator="none"
          inlineWrap="keep-inline"
        >
          {percent === undefined ? null : `${Math.round(percent)}%`}
        </Field>
      </PanelSectionRow>
      <PanelSectionRow>
        <ProgressBar
          nProgress={percent ?? 0}
          indeterminate={percent === undefined}
        />
      </PanelSectionRow>
    </>
  );
}
