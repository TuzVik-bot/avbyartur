import type { CSSProperties } from "react";

const background = "#edf2ff";
const petalColors = ["#2f64d6", "#4d83e5", "#3470dc", "#2460ca"];

export function CornflowerMark({ size = 24, safeMargin = 0, rounded = true }: {
  size?: number;
  safeMargin?: number;
  rounded?: boolean;
}) {
  const petalSize: CSSProperties = {
    position: "absolute",
    left: "40%",
    top: "1%",
    width: "20%",
    height: "51%",
    borderRadius: "50% 50% 16% 16%",
    transformOrigin: "50% 96%"
  };

  return (
    <span
      aria-hidden="true"
      style={{
        position: "relative",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        flex: "none",
        width: size,
        height: size,
        borderRadius: rounded ? Math.max(3, size * 0.16) : 0,
        backgroundColor: background
      }}
    >
      <span
        style={{
          position: "relative",
          display: "block",
          flex: "none",
          width: size * (1 - safeMargin * 2),
          height: size * (1 - safeMargin * 2)
        }}
      >
        {Array.from({ length: 12 }, (_, index) => (
          <span
            key={index}
            style={{
              ...petalSize,
              backgroundColor: petalColors[index % petalColors.length],
              transform: `rotate(${index * 30}deg)`
            }}
          />
        ))}
        <span
          style={{
            position: "absolute",
            left: "32%",
            top: "32%",
            width: "36%",
            height: "36%",
            borderRadius: "50%",
            backgroundColor: "#1f4ca6",
            display: "flex",
            alignItems: "center",
            justifyContent: "center"
          }}
        >
          <span style={{ width: "30%", height: "30%", borderRadius: "50%", backgroundColor: "#f1c64f" }} />
        </span>
      </span>
    </span>
  );
}
