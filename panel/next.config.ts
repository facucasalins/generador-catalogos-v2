import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  images: {
    // Las placas viven en Cloudinary y las fotos de producto en Tiendanube.
    remotePatterns: [
      { protocol: "https", hostname: "res.cloudinary.com" },
      { protocol: "https", hostname: "**.mitiendanube.com" },
    ],
  },
};

export default nextConfig;
