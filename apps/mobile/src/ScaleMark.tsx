// Scale-reference marking (plan §6.3). The officer lays an ISO ID-1 card on the
// package's display face, photographs it with the in-app camera, then drags four
// corner handles onto the card and — optionally — four onto the display panel.
// The phone only records where the handles were dragged in image pixels; the
// server's scale module owns every physical conclusion and refuses mis-marked
// quads instead of guessing.
import { useRef, useState } from "react";
import {
  Image, Pressable, StyleSheet, Text, View,
} from "react-native";
import { cardMarksPlausible, toImagePoints, type Point } from "./quad";
import type { ScaleReference } from "./types";

const HANDLE = 30;

type Step = "card" | "panel";

export function ScaleMark({imageUri, onDone, onCancel}: {
  imageUri: string;
  onDone: (reference: ScaleReference) => void;
  onCancel: () => void;
}) {
  const [container, setContainer] = useState({width: 0, height: 0});
  const [natural, setNatural] = useState({width: 0, height: 0});
  const [card, setCard] = useState<Point[]>([
    {x: 0.18, y: 0.2}, {x: 0.42, y: 0.2}, {x: 0.42, y: 0.32}, {x: 0.18, y: 0.32},
  ]);
  const [panel, setPanel] = useState<Point[]>([
    {x: 0.55, y: 0.4}, {x: 0.85, y: 0.4}, {x: 0.85, y: 0.75}, {x: 0.55, y: 0.75},
  ]);
  const [step, setStep] = useState<Step>("card");
  const drag = useRef<number | null>(null);
  const imageWidth = natural.width;
  const imageHeight = natural.height;

  // Handles live in normalised image coordinates so marks survive any resize;
  // they are only converted to absolute pixels at submission time.
  const scale = container.width && container.height && imageWidth && imageHeight
    ? Math.min(container.width / imageWidth, container.height / imageHeight)
    : 0;
  const fitted = scale > 0
    ? {width: imageWidth * scale, height: imageHeight * scale}
    : null;

  const current = step === "card" ? card : panel;
  const setCurrent = step === "card" ? setCard : setPanel;

  const cardPlausible = cardMarksPlausible(
    card.map((point) => ({x: point.x * imageWidth, y: point.y * imageHeight})));

  function finish() {
    onDone({
      type: "ISO_ID1_CARD",
      data: {
        quad: toImagePoints(card, 1, 1, imageWidth, imageHeight),
        panel_quad: toImagePoints(panel, 1, 1, imageWidth, imageHeight),
      },
    });
  }

  function onGrant(event: {nativeEvent: {locationX: number; locationY: number}}) {
    if (!fitted) return;
    const at = event.nativeEvent;
    let best = -1;
    let bestDistance = HANDLE * 1.6;
    current.forEach((handle, index) => {
      const gap = Math.hypot(at.locationX - handle.x * fitted.width,
        at.locationY - handle.y * fitted.height);
      if (gap < bestDistance) { bestDistance = gap; best = index; }
    });
    drag.current = best;
  }

  function onMove(event: {nativeEvent: {locationX: number; locationY: number}}) {
    if (!fitted || drag.current === null) return;
    const x = Math.min(Math.max(event.nativeEvent.locationX, 0), fitted.width);
    const y = Math.min(Math.max(event.nativeEvent.locationY, 0), fitted.height);
    const index = drag.current;
    setCurrent((previous) => previous.map((point, pointIndex) =>
      pointIndex === index ? {x: x / fitted.width, y: y / fitted.height} : point));
  }

  return (
    <View style={styles.page}>
      <View style={styles.header}>
        <Text style={styles.title}>
          {step === "card" ? "Mark the card corners" : "Mark the display panel"}
        </Text>
        <Pressable onPress={onCancel}><Text style={styles.link}>Cancel</Text></Pressable>
      </View>
      <Text style={styles.hint}>
        {step === "card"
          ? "Drag each numbered handle onto a corner of the ID-1 card. "
            + "The card must lie flat on the package's front face."
          : "Drag the handles onto the corners of the principal display panel "
            + "(the face that carries the declarations)."}
      </Text>
      <View
        style={styles.frame}
        onLayout={({nativeEvent}) => setContainer(
          {width: nativeEvent.layout.width, height: nativeEvent.layout.height})}
        onStartShouldSetResponder={() => fitted !== null}
        onMoveShouldSetResponder={() => fitted !== null}
        onResponderGrant={onGrant}
        onResponderMove={onMove}
        onResponderRelease={() => { drag.current = null; }}
      >
        {fitted && imageWidth > 0 && (
          <View style={{width: fitted.width, height: fitted.height}}>
            <Image
              source={{uri: imageUri}}
              style={styles.image}
              resizeMode="contain"
              onLoad={({nativeEvent: {source}}) => setNatural(
                {width: source.width, height: source.height})} />
            {current.map((point, index) => (
              <View key={`${step}-${index}`} style={[styles.handle, {
                left: point.x * fitted.width - HANDLE / 2,
                top: point.y * fitted.height - HANDLE / 2,
              }]}>
                <Text style={styles.handleText}>{index + 1}</Text>
              </View>
            ))}
          </View>
        )}
      </View>
      <View style={styles.footer}>
        {step === "card" && !cardPlausible && (
          <Text style={styles.warning}>
            These marks do not look like an ID-1 card. Adjust them or remove the
            scale reference before submitting.
          </Text>
        )}
        <View style={styles.actions}>
          {step === "card"
            ? <Pressable onPress={() => onDone({type: "NONE"})}>
                <Text style={styles.link}>Skip — no scale reference</Text>
              </Pressable>
            : <Pressable onPress={finish}>
                <Text style={styles.link}>Skip panel marks</Text>
              </Pressable>}
          <Pressable
            style={[styles.primary, step === "card" && !cardPlausible && styles.disabled]}
            disabled={step === "card" && !cardPlausible}
            onPress={() => step === "card" ? setStep("panel") : finish()}>
            <Text style={styles.primaryText}>
              {step === "card" ? "Next: display panel" : "Save scale reference"}
            </Text>
          </Pressable>
        </View>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  page: {flex: 1, backgroundColor: "#fafbf7", paddingTop: 12},
  header: {flexDirection: "row", alignItems: "center", paddingHorizontal: 18,
    justifyContent: "space-between"},
  title: {fontSize: 18, fontWeight: "800", color: "#17231d", flex: 1},
  link: {color: "#1e6647", fontWeight: "700", fontSize: 14},
  hint: {fontSize: 13, lineHeight: 19, color: "#627068", paddingHorizontal: 18,
    marginTop: 8},
  frame: {flex: 1, margin: 18, alignItems: "center", justifyContent: "center"},
  image: {width: "100%", height: "100%", borderRadius: 10},
  handle: {position: "absolute", width: HANDLE, height: HANDLE, borderRadius: 13,
    backgroundColor: "#1e6647", borderWidth: 2, borderColor: "white",
    alignItems: "center", justifyContent: "center"},
  handleText: {color: "white", fontSize: 11, fontWeight: "900"},
  footer: {padding: 18, gap: 10},
  warning: {color: "#8a5a10", backgroundColor: "#fdf5e3", borderRadius: 8,
    padding: 11, fontSize: 13},
  actions: {flexDirection: "row", alignItems: "center", justifyContent:
    "space-between", gap: 12},
  primary: {minHeight: 48, borderRadius: 11, backgroundColor: "#1e6647",
    alignItems: "center", justifyContent: "center", paddingHorizontal: 18, flex: 1},
  primaryText: {color: "white", fontSize: 15, fontWeight: "800"},
  disabled: {opacity: .45},
});