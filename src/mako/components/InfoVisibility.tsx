import {
  DialogButton,
  GamepadButton,
  gamepadDialogClasses,
  type GamepadEvent,
} from "@decky/ui";
import {
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
  type FocusEventHandler,
  type ReactNode,
} from "react";
import { usePersistentCollapseState } from "../hooks/usePersistentCollapseState";
import t from "../i18n/i18n";
import { findFocusScrollContainer } from "../utils/focusScrollUtils";
import { MakoFocusable, makoDialogButtonStyle } from "./MakoUi";
import { InfoHiddenContext } from "./MakoInfo";

// Use Decky's resolved class, never a hard-coded Steam CSS module name.
const infoSelector = `[data-mako-info="true"], .${gamepadDialogClasses.FieldDescription}, .Mako_OptionDescription`;
const ribbonSelector = '[data-mako-info-toggle="true"]';
const focusGroupSelector = '[data-mako-focus-scroll="group"]';

function scrollFocusGroup(group: HTMLElement) {
  const scroller = findFocusScrollContainer(group);
  if (!scroller) {
    group.scrollIntoView({ block: "start", inline: "nearest", behavior: "auto" });
    return;
  }

  const bounds = group.getBoundingClientRect();
  const viewportTop =
    scroller === group.ownerDocument.scrollingElement
      ? 0
      : scroller.getBoundingClientRect().top + scroller.clientTop;
  // Leave more room for the selected tab's controls, keeping the whole grid
  // visible on short panels and respecting both ends of the scroll range.
  const inset = Math.max(0, scroller.clientHeight / 3 - bounds.height / 2);
  scroller.scrollTop = Math.max(
    0,
    Math.min(
      scroller.scrollHeight - scroller.clientHeight,
      scroller.scrollTop + bounds.top - viewportTop - inset,
    ),
  );
}

function adjacentControl(
  panel: Element,
  source: HTMLElement,
): HTMLElement | null {
  const view = source.ownerDocument.defaultView;
  const controls = Array.from(
    panel.querySelectorAll<HTMLElement>(
      "button, input, select, textarea, a[href], [tabindex]",
    ),
  ).filter((control) => {
    if (
      control.tabIndex < 0 ||
      control.contains(source) ||
      control.matches(":disabled") ||
      control.closest(
        `${infoSelector}, ${ribbonSelector}, [hidden], [inert], [aria-disabled="true"], .disabled`,
      )
    )
      return false;

    for (
      let element: HTMLElement | null = control;
      element;
      element = element.parentElement
    ) {
      const style = view?.getComputedStyle(element);
      if (
        style?.display === "none" ||
        style?.visibility === "hidden" ||
        style?.visibility === "collapse"
      )
        return false;
      if (element === panel) break;
    }
    return true;
  });

  // DOM order follows the panel's column navigation. Prefer continuing down
  // the settings; at the end, stay near the previous surviving control.
  return (
    controls.find(
      (control) =>
        source.compareDocumentPosition(control) &
        Node.DOCUMENT_POSITION_FOLLOWING,
    ) ??
    controls[controls.length - 1] ??
    null
  );
}

/** Keep help visibility local to the panel, independent of game profiles. */
export function InfoVisibility({ children }: { children: ReactNode }) {
  const [hidden, setHidden] = usePersistentCollapseState(
    "mako-info-hidden",
    false,
    "MAKO Decky information",
  );
  const [focused, setFocused] = useState(false);
  const ribbon = useRef<HTMLDivElement>(null);
  const scrollFrame = useRef<number>();
  const pendingFocusGroup = useRef<HTMLElement | null>(null);
  const lastFocusedControl = useRef<HTMLElement | null>(null);
  const activeFocusedControl = useRef<HTMLElement | null>(null);
  const focusAnchor = useRef<{
    target: HTMLElement;
    top: number;
    scroller: HTMLElement | null;
  }>();
  const label = hidden
    ? t("CONTENT_SHOW_INFO", "Show info")
    : t("CONTENT_HIDE_INFO", "Hide info");

  const cancelScroll = () => {
    if (scrollFrame.current !== undefined) {
      cancelAnimationFrame(scrollFrame.current);
      scrollFrame.current = undefined;
    }
  };

  useEffect(() => cancelScroll, []);

  useLayoutEffect(() => {
    const anchor = focusAnchor.current;
    if (!anchor) return;
    const target = anchor.target.isConnected
      ? anchor.target
      : ribbon.current?.querySelector("button");
    // Refocusing a surviving control alone emits no new focus event. Restore
    // its screen position explicitly, after descriptions have changed height.
    target?.focus({ preventScroll: true });
    if (target === anchor.target && anchor.scroller) {
      anchor.scroller.scrollTop +=
        target.getBoundingClientRect().top - anchor.top;
    }
    focusAnchor.current = undefined;
  }, [hidden]);

  const queueFocusScroll = (
    panel: HTMLElement,
    target: HTMLElement,
    previous: Element | null,
    gamepad: boolean,
  ) => {
    if (!panel.contains(target)) return;
    // Steam may emit both controller and browser focus for one move. Keep the
    // original request, including its entry direction, when that happens.
    if (activeFocusedControl.current === target) return;
    cancelScroll();
    lastFocusedControl.current = target;
    activeFocusedControl.current = target;
    if (focusAnchor.current || target.closest(ribbonSelector)) {
      pendingFocusGroup.current = null;
      return;
    }

    const group = target.closest<HTMLElement>(focusGroupSelector);
    const previousGroup = previous?.closest(focusGroupSelector);
    if (!group || !group.contains(previous)) {
      // Panel DOM order follows vertical navigation. Only an entry from a
      // control above the grid should reposition it; unknown origins stay put.
      pendingFocusGroup.current =
        group &&
        previous &&
        panel.contains(previous) &&
        !previous.contains(group) &&
        (group.compareDocumentPosition(previous) &
          Node.DOCUMENT_POSITION_PRECEDING)
          ? group
          : null;
    }

    // Carry entry placement through rapid moves within the grid. Leaving it
    // only reveals the next control, without recentering the panel.
    scrollFrame.current = requestAnimationFrame(() => {
      scrollFrame.current = undefined;
      if (
        target.isConnected &&
        activeFocusedControl.current === target &&
        (gamepad || target.ownerDocument.activeElement === target)
      ) {
        if (group && pendingFocusGroup.current === group) {
          scrollFocusGroup(group);
        } else {
          target.scrollIntoView({
            block:
              group ||
              previousGroup ||
              target.closest('[data-mako-focus-scroll="nearest"]')
                ? "nearest"
                : "center",
            inline: "nearest",
            behavior: "auto",
          });
        }
        pendingFocusGroup.current = null;
      }
    });
  };

  const onFocusCapture: FocusEventHandler<HTMLDivElement> = (event) => {
    // Steam portals can belong to another window: instanceof Element checks
    // against this module's window would reject their valid relatedTarget.
    const previous =
      event.relatedTarget?.nodeType === 1
        ? event.relatedTarget
        : lastFocusedControl.current;
    queueFocusScroll(event.currentTarget, event.target, previous, false);
  };

  const onGamepadFocus = (event: GamepadEvent) => {
    const target = event.target as HTMLElement | null;
    if (target?.nodeType !== 1) return;
    queueFocusScroll(
      event.currentTarget as HTMLElement,
      target,
      lastFocusedControl.current,
      true,
    );
  };

  const clearActiveFocus = (target: EventTarget | null) => {
    if (activeFocusedControl.current !== target) return;
    cancelScroll();
    activeFocusedControl.current = null;
  };

  const onBlurCapture: FocusEventHandler<HTMLDivElement> = (event) => {
    if (activeFocusedControl.current !== event.target) return;
    clearActiveFocus(event.target);
    if (
      event.relatedTarget &&
      !event.currentTarget.contains(event.relatedTarget)
    ) {
      lastFocusedControl.current = null;
      pendingFocusGroup.current = null;
    }
  };

  const toggle = (source?: HTMLElement) => {
    cancelScroll();
    pendingFocusGroup.current = null;
    const panel = ribbon.current?.closest(".Mako_InfoVisibility");
    const activeElement = ribbon.current?.ownerDocument
      .activeElement as HTMLElement | null;
    let target = source ?? activeElement;
    const sourceTop = target?.getBoundingClientRect().top;
    if (
      target &&
      panel?.contains(target) &&
      !hidden &&
      target.closest(infoSelector)
    ) {
      target = adjacentControl(panel, target);
    }
    if (!target || !panel?.contains(target)) {
      target = ribbon.current?.querySelector("button") ?? null;
    }
    if (target) {
      focusAnchor.current = {
        target,
        top: sourceTop ?? target.getBoundingClientRect().top,
        scroller: target.closest(ribbonSelector)
          ? null
          : findFocusScrollContainer(target),
      };
      target.focus({ preventScroll: true });
    }
    setHidden((current) => !current);
  };

  const onButtonDown = (event: GamepadEvent) => {
    if (event.detail.button !== GamepadButton.BUMPER_RIGHT) return;
    event.preventDefault();
    event.stopPropagation();
    if (!event.detail.is_repeat) toggle(event.target as HTMLElement);
  };

  return (
    <MakoFocusable
      className={
        hidden ? "Mako_InfoVisibility Mako_InfoHidden" : "Mako_InfoVisibility"
      }
      flow-children="column"
      onButtonDown={onButtonDown}
      onFocusCapture={onFocusCapture}
      onBlurCapture={onBlurCapture}
      onGamepadFocus={onGamepadFocus}
      onGamepadBlur={(event) => clearActiveFocus(event.target)}
    >
      <style>{`
        .Mako_InfoVisibility .${gamepadDialogClasses.FieldDescription},
        .Mako_InfoVisibility .Mako_OptionDescription,
        .Mako_InfoVisibility .Mako_OptionMessage {
          font-size: 10px !important;
          line-height: 14px !important;
        }
        .Mako_InfoVisibility.DesktopUI .${gamepadDialogClasses.FieldDescription},
        .Mako_InfoVisibility.DesktopUI .Mako_OptionDescription,
        .Mako_InfoVisibility.DesktopUI .Mako_OptionMessage,
        .DesktopUI .Mako_InfoVisibility .${gamepadDialogClasses.FieldDescription},
        .DesktopUI .Mako_InfoVisibility .Mako_OptionDescription,
        .DesktopUI .Mako_InfoVisibility .Mako_OptionMessage {
          font-size: 11px !important;
          line-height: 16px !important;
        }
        .Mako_InfoHidden .${gamepadDialogClasses.FieldDescription},
        .Mako_InfoHidden .Mako_OptionDescription {
          display: none !important;
        }
        .Mako_InfoHidden [data-mako-update-notice="true"] {
          background: none !important;
          border: none !important;
          padding: 0 !important;
        }
      `}</style>
      <InfoHiddenContext.Provider value={hidden}>
        {children}
      </InfoHiddenContext.Provider>
      <div
        ref={ribbon}
        data-mako-info-toggle="true"
        style={{
          position: "sticky",
          bottom: "8px",
          zIndex: 5,
          display: "flex",
          justifyContent: "flex-end",
          margin: "8px 12px",
          pointerEvents: "none",
        }}
      >
        <DialogButton
          aria-label={label}
          aria-pressed={hidden}
          onClick={() => toggle()}
          onGamepadFocus={() => setFocused(true)}
          onGamepadBlur={() => setFocused(false)}
          style={{
            ...makoDialogButtonStyle(focused),
            display: "flex",
            alignItems: "center",
            gap: "6px",
            width: "auto",
            minWidth: 0,
            height: "28px",
            padding: "4px 9px",
            borderRadius: "6px",
            fontSize: "11px",
            lineHeight: 1.2,
            pointerEvents: "auto",
          }}
        >
          <span
            aria-hidden="true"
            style={{
              border: "1px solid rgba(200, 230, 240, 0.6)",
              borderRadius: "3px",
              padding: "1px 4px",
              fontSize: "10px",
              fontWeight: 700,
            }}
          >
            R1
          </span>
          {label}
        </DialogButton>
      </div>
    </MakoFocusable>
  );
}
