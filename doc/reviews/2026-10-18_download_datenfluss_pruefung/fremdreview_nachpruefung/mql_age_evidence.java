package rest;

import java.io.File;
import java.util.*;
import com.google.gson.GsonBuilder;

/** Read-only: only public signal IDs, proven ages and aggregate counts are emitted. */
public class mql_age_evidence {
    public static void main(String[] args) {
        File root = new File(args[0]);
        ProviderAge age = new ProviderAge();
        Map<String,Object> out = new LinkedHashMap<>();
        out.put("source", ProviderAge.SOURCE);
        out.put("readOnly", true);
        out.put("networkRequests", 0);
        long began = System.nanoTime();
        for (String version : new String[]{"mql4", "mql5"}) {
            File[] files = new File(root, version).listFiles(f -> f.isFile() && f.getName().endsWith("_root.html"));
            Set<String> ids = new TreeSet<>();
            if (files != null) for (File f : files) {
                String id = ProviderFiles.extractSignalId(f.getName());
                if (id != null) ids.add(id);
            }
            int known=0, young=0, mature=0;
            List<String> unknown = new ArrayList<>();
            Map<String,Integer> samples = new LinkedHashMap<>();
            for (String id : ids) {
                Integer weeks = age.weeks(root, id, version);
                if (weeks == null) unknown.add(id);
                else {
                    known++;
                    if (weeks < 26) young++; else mature++;
                    if (samples.size() < 3 || Arrays.asList("2295882","2381807","2371777","2350211","2265877","2379208").contains(id)) samples.put(id,weeks);
                }
            }
            Map<String,Object> result = new LinkedHashMap<>();
            result.put("htmlFiles", files == null ? 0 : files.length);
            result.put("uniqueNumericIds", ids.size());
            result.put("provenWeeks", known);
            result.put("lessThan26Weeks", young);
            result.put("atLeast26Weeks", mature);
            result.put("unknownIds", unknown);
            result.put("samples", samples);
            out.put(version,result);
        }
        out.put("firstPassMs", (System.nanoTime()-began)/1000000);
        began=System.nanoTime();
        for (String version : new String[]{"mql4","mql5"}) {
            File[] files = new File(root,version).listFiles(f -> f.isFile() && f.getName().endsWith("_root.html"));
            if (files!=null) for(File f:files) age.weeks(root,ProviderFiles.extractSignalId(f.getName()),version);
        }
        out.put("cachedPassMs",(System.nanoTime()-began)/1000000);
        System.out.println(new GsonBuilder().setPrettyPrinting().create().toJson(out));
    }
}
