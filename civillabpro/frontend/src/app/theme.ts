import { createTheme } from "@mui/material/styles";

/**
 * Dense, engineering-software look: small type, tight controls, square-ish corners.
 * Light and dark schemes are both defined; MUI writes the choice as a class on <html>,
 * which the CSS tokens in index.css and Tailwind's dark: variant follow.
 */
export const theme = createTheme({
  cssVariables: { colorSchemeSelector: "class" },
  colorSchemes: {
    light: {
      palette: {
        primary: { main: "#1f5fbf" },
        success: { main: "#17803f" },
        error: { main: "#c0352b" },
        warning: { main: "#9a6700" },
        background: { default: "#eef1f5", paper: "#ffffff" },
        text: { primary: "#17202b", secondary: "#4b5766" },
        divider: "#d5dbe3",
      },
    },
    dark: {
      palette: {
        primary: { main: "#5ea0f0" },
        success: { main: "#3fb96b" },
        error: { main: "#ef6b60" },
        warning: { main: "#e0a83a" },
        background: { default: "#0b0f14", paper: "#131a22" },
        text: { primary: "#e6ebf1", secondary: "#a9b4c0" },
        divider: "#26313d",
      },
    },
  },
  shape: { borderRadius: 4 },
  typography: {
    fontFamily: '"Inter", "Segoe UI", system-ui, -apple-system, "Helvetica Neue", Arial, sans-serif',
    fontSize: 13,
    button: { textTransform: "none", fontWeight: 600 },
    h6: { fontSize: 15, fontWeight: 650 },
    subtitle2: { fontSize: 12, fontWeight: 650 },
  },
  components: {
    MuiButton: { defaultProps: { size: "small", disableElevation: true } },
    MuiIconButton: { defaultProps: { size: "small" } },
    MuiTextField: { defaultProps: { size: "small", variant: "outlined" } },
    MuiSelect: { defaultProps: { size: "small" } },
    MuiTooltip: { defaultProps: { arrow: true, enterDelay: 400 } },
    MuiTableCell: { styleOverrides: { root: { padding: "6px 10px", fontSize: 13 }, head: { fontWeight: 650, fontSize: 12 } } },
    MuiDialogTitle: { styleOverrides: { root: { fontSize: 15, fontWeight: 650, padding: "14px 20px" } } },
    MuiChip: { defaultProps: { size: "small" } },
    MuiPaper: { styleOverrides: { root: { backgroundImage: "none" } } },
  },
});
