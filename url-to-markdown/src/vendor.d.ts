declare module "turndown-plugin-gfm" {
  import TurndownService from "turndown";

  type Plugin = (service: TurndownService) => void;

  const turndownPluginGfm: {
    gfm: Plugin;
    tables: Plugin;
    strikethrough: Plugin;
    taskListItems: Plugin;
  };

  export = turndownPluginGfm;
}
