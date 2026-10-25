export function taskLimitsPayload(values:Record<string,any>,revision:number){
  return {revision,teacher_count:values.teacher_count,max_students:values.max_students,
    ...(Object.hasOwn(values,'room_id')?{room_id:values.room_id??null}:{}),
    ...(Array.isArray(values.slots)?{slots:values.slots}:{})};
}

export function taskCourseInfo(task:any){
  const imported=task?.source?.course_metadata||{};
  return {
    name:imported.name??task?.name,code:imported.code??task?.code,
    credits:imported.credits??task?.credits,required_hours:imported.required_hours??task?.required_hours,
    category:imported.category??task?.category,department:task?.source?.major??task?.department,
    group:task?.group,
  };
}
