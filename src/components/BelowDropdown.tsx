import type { ReactNode } from "react";
import {
  DialogButton,
  DialogHeader,
  Field,
  Focusable,
  ModalRoot,
  showModal,
  type DropdownOption,
  type SingleDropdownOption,
} from "@decky/ui";

type Props = {
  label: ReactNode;
  description?: ReactNode;
  rgOptions: DropdownOption[];
  selectedOption: unknown;
  disabled?: boolean;
  onChange?(o: SingleDropdownOption): void;
  menuLabel?: string;
  strDefaultLabel?: string;
};

function flat(options: DropdownOption[]): SingleDropdownOption[] {
  return options.flatMap((o) => (o.options ? flat(o.options) : [o as SingleDropdownOption]));
}

// Steam hides scrollbars everywhere; a long list shows one so it's clear there are more choices below
const LIST_CSS = `
.multifg-picker-list::-webkit-scrollbar { display: block; width: 6px; }
.multifg-picker-list::-webkit-scrollbar-track { background: rgba(255, 255, 255, 0.1); border-radius: 3px; }
.multifg-picker-list::-webkit-scrollbar-thumb { background: rgba(255, 255, 255, 0.55); border-radius: 3px; }
`;

function PickerModal({
  title,
  options,
  selected,
  onPick,
  closeModal,
}: {
  title: ReactNode;
  options: SingleDropdownOption[];
  selected: unknown;
  onPick(o: SingleDropdownOption): void;
  closeModal?(): void;
}) {
  return (
    <ModalRoot onCancel={closeModal} closeModal={closeModal}>
      <DialogHeader>{title}</DialogHeader>
      <style>{LIST_CSS}</style>
      <Focusable
        className="multifg-picker-list"
        flow-children="column"
        style={{
          display: "flex",
          flexDirection: "column",
          gap: "6px",
          maxHeight: "60vh",
          overflowY: "auto",
          paddingRight: options.length > 6 ? "10px" : undefined,
        }}
      >
        {options.map((o, i) => (
          <DialogButton
            key={i}
            style={{ textAlign: "left" }}
            onClick={() => {
              closeModal?.();
              onPick(o);
            }}
          >
            {o.data === selected ? "✓ " : ""}
            {o.label}
          </DialogButton>
        ))}
      </Focusable>
    </ModalRoot>
  );
}

// A choice on its own full-width line under its label (Steam's DropdownItem keeps it on the label's line, which
// cuts long game names and choices short). The list opens as a centred Steam dialog: the SteamOS beta client
// opens a Dropdown's own menu off the right edge of the screen from the Quick Access Menu.
export function BelowDropdown({
  label,
  description,
  rgOptions,
  selectedOption,
  disabled,
  onChange,
  menuLabel,
  strDefaultLabel,
}: Props) {
  const options = flat(rgOptions);
  const current = options.find((o) => o.data === selectedOption);
  const open = () =>
    showModal(
      <PickerModal
        title={menuLabel ?? label}
        options={options}
        selected={selectedOption}
        onPick={(o) => onChange?.(o)}
      />,
    );
  return (
    <Field
      label={label}
      description={description}
      childrenLayout="below"
      childrenContainerWidth="max"
    >
      <DialogButton
        disabled={disabled}
        onClick={open}
        style={{ display: "flex", justifyContent: "space-between", alignItems: "center", textAlign: "left" }}
      >
        <span>{current?.label ?? strDefaultLabel ?? ""}</span>
        <span>▾</span>
      </DialogButton>
    </Field>
  );
}
