type Props = {
  id: string;
  label: string;
  value: string;
  multiline?: boolean;
  onChange: (value: string) => void;
  placeholder?: string;
  active?: boolean;
  onFocus: (id: string) => void;
};

export function EditableDocumentBlock({ id,label,value,multiline=true,onChange,placeholder,active=false,onFocus }:Props) {
  return <section className={`v2-editable-block ${active?"is-active":""}`}>
    <label htmlFor={id}>{label}</label>
    <textarea id={id} rows={multiline?4:1} value={value} placeholder={placeholder} onChange={(event)=>onChange(event.target.value)} onFocus={()=>onFocus(id)} />
  </section>;
}
