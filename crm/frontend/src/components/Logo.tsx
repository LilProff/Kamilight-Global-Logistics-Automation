export default function Logo({ variant = "black", height = 28 }: { variant?: "black" | "white"; height?: number }) {
  return (
    <img
      src={variant === "white" ? "/logo-white.png" : "/logo-black.png"}
      alt="Kamilight"
      style={{ height, width: "auto", display: "block" }}
    />
  );
}
