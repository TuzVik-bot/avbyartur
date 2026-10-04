import { ImageResponse } from "next/og";
import { CornflowerMark } from "@/components/cornflower-mark";

export const size = { width: 32, height: 32 };
export const contentType = "image/png";

export default function Icon() {
  return new ImageResponse(<CornflowerMark size={size.width} safeMargin={0.08} rounded={false} />, size);
}
